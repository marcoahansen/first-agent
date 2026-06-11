"""Servidor MCP "POI Finder" — Etapa 2 do desafio final da trilha.

Expõe uma ferramenta MCP (`poi_find`, conceitualmente `poi.find`) que recebe uma
coordenada + raio + categorias e devolve uma lista estruturada de pontos de
interesse reais. O contrato forte (tipos + docstring) é o que o FastMCP usa para
gerar o manifesto que o agente LangChain enxerga.

Provider AGNÓSTICO (decidido pela presença de chave):
  • OPENTRIPMAP_API_KEY vazio  → Overpass / OpenStreetMap   (sem chave, default)
  • OPENTRIPMAP_API_KEY setado → OpenTripMap                 (como pede o exercício)

Como rodar:
  • stdio (default, usado pelo agente):   python poi_server.py
  • HTTP streamable (inspeção/manual):    python poi_server.py --http   # :8000/mcp

Contrato:
  poi_find(lat, lon, radius_m, kinds, limit) -> list[POI]
  POI = {id, name, kind, lat, lon, dist_m, preview, wikidata, source}
"""

from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

# IMPORTANTE: o transporte stdio do MCP NÃO herda o os.environ completo do agente
# (usa um env mínimo). Por isso o servidor lê o .env do projeto por conta própria.
load_dotenv()

OPENTRIPMAP_API_KEY = os.getenv("OPENTRIPMAP_API_KEY", "").strip()
PROVIDER = "opentripmap" if OPENTRIPMAP_API_KEY else "overpass"

USER_AGENT = "desafio-final-poi-finder/1.0 (curso LLM agents)"  # Overpass exige UA (senão 406)

# Espelhos do Overpass — tenta em ordem até um responder 200.
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
OPENTRIPMAP_BASE = "https://api.opentripmap.com/0.1/en/places"

mcp = FastMCP(name="poi-finder")


# ───────────────────────────── contrato do POI ─────────────────────────────
class POI(BaseModel):
    """Ponto de interesse normalizado (mesma forma para qualquer provider)."""

    id: str = Field(description="ID estável (xid do OpenTripMap ou 'node/123' do OSM)")
    name: str
    kind: str = Field(description="Categoria principal (vocabulário do provider)")
    lat: float
    lon: float
    dist_m: Optional[int] = Field(default=None, description="Distância em metros até o ponto consultado")
    preview: str = Field(default="", description="Descrição/resumo curto (truncado p/ o LLM)")
    wikidata: Optional[str] = None
    source: str = Field(description="Provider de origem: 'overpass-osm' ou 'opentripmap'")


# ─────────────────────── cache simples em memória (TTL) ────────────────────
# Evita bater na API repetidamente para a mesma busca (rate-limit friendly).
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 minutos


def _cache_key(lat: float, lon: float, radius_m: int, kinds: str, limit: int) -> str:
    return f"{PROVIDER}:{round(lat, 4)},{round(lon, 4)}:{radius_m}:{kinds.strip().lower()}:{limit}"


def _cache_get(key: str) -> Optional[list[dict]]:
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _cache_put(key: str, value: list[dict]) -> None:
    _CACHE[key] = (time.time(), value)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


# ───────────────────────── provider: Overpass / OSM ────────────────────────
# Mapeia categorias amigáveis (vocabulário próximo ao do OpenTripMap) → filtros OSM.
OSM_KINDS: dict[str, list[str]] = {
    "museums": ['"tourism"="museum"'],
    "museum": ['"tourism"="museum"'],
    "cultural": ['"tourism"="museum"', '"tourism"="gallery"', '"tourism"="artwork"', '"amenity"="arts_centre"', '"amenity"="theatre"'],
    "restaurants": ['"amenity"="restaurant"'],
    "restaurant": ['"amenity"="restaurant"'],
    "foods": ['"amenity"="restaurant"', '"amenity"="cafe"', '"amenity"="fast_food"'],
    "cafes": ['"amenity"="cafe"'],
    "bars": ['"amenity"="bar"', '"amenity"="pub"'],
    "parks": ['"leisure"="park"'],
    "park": ['"leisure"="park"'],
    "gardens": ['"leisure"="garden"'],
    "natural": ['"leisure"="park"', '"natural"="beach"', '"leisure"="garden"', '"natural"="peak"'],
    "beaches": ['"natural"="beach"'],
    "viewpoints": ['"tourism"="viewpoint"'],
    "historic": ['"historic"~"."'],
    "monuments": ['"historic"="monument"', '"historic"="memorial"'],
    "architecture": ['"historic"~"."', '"building"="church"', '"building"="cathedral"'],
    "religion": ['"amenity"="place_of_worship"'],
    "churches": ['"building"~"church|cathedral"', '"amenity"="place_of_worship"'],
    "hotels": ['"tourism"="hotel"'],
    "accomodations": ['"tourism"~"hotel|hostel|guest_house|apartment"'],
    "shops": ['"shop"~"."'],
    "malls": ['"shop"="mall"'],
    "attractions": ['"tourism"="attraction"'],
    "interesting_places": ['"tourism"~"attraction|museum|viewpoint|gallery|artwork"', '"historic"~"."'],
    "amusements": ['"tourism"="theme_park"', '"leisure"="water_park"'],
}
DEFAULT_OSM_FILTERS = [
    '"tourism"~"attraction|museum|viewpoint|gallery|artwork"',
    '"historic"~"."',
    '"leisure"="park"',
]


def _osm_filters(kinds: str) -> list[str]:
    """Converte 'museums,cultural' → lista de filtros OSM (ou default se vazio)."""
    kinds = (kinds or "").strip().lower()
    if not kinds:
        return DEFAULT_OSM_FILTERS
    out: list[str] = []
    for raw in kinds.split(","):
        k = raw.strip()
        if not k:
            continue
        if k in OSM_KINDS:
            out.extend(OSM_KINDS[k])
        else:
            # categoria desconhecida → tenta casar como amenity OU tourism cru.
            out.append(f'"amenity"="{k}"')
            out.append(f'"tourism"="{k}"')
    # dedupe preservando ordem
    seen: set[str] = set()
    return [f for f in out if not (f in seen or seen.add(f))]


def _osm_kind_label(tags: dict) -> str:
    for key in ("tourism", "historic", "leisure", "amenity", "shop", "natural"):
        if tags.get(key):
            return f"{key}:{tags[key]}"
    return "poi"


def _osm_to_poi(el: dict, lat0: float, lon0: float) -> Optional[dict]:
    tags = el.get("tags") or {}
    name = tags.get("name") or tags.get("name:en") or tags.get("brand") or ""
    if not name:
        return None
    if el.get("type") == "node":
        la, lo = el.get("lat"), el.get("lon")
    else:  # way/relation → usa o center (pedido com 'out center')
        c = el.get("center") or {}
        la, lo = c.get("lat"), c.get("lon")
    if la is None or lo is None:
        return None
    addr = " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")]))
    preview = "; ".join(
        b for b in (tags.get("cuisine"), addr, tags.get("opening_hours"), tags.get("website")) if b
    )[:280]
    return POI(
        id=f"{el.get('type')}/{el.get('id')}",
        name=name,
        kind=_osm_kind_label(tags),
        lat=la,
        lon=lo,
        dist_m=_haversine_m(lat0, lon0, la, lo),
        preview=preview,
        wikidata=tags.get("wikidata"),
        source="overpass-osm",
    ).model_dump()


async def _query_overpass(
    client: httpx.AsyncClient, lat: float, lon: float, radius_m: int, kinds: str, limit: int
) -> list[dict]:
    filters = _osm_filters(kinds)
    cap = min(max(limit * 4, 40), 80)  # busca extra → dedupe → ordena por distância → corta
    union = "".join(f"  nwr(around:{radius_m},{lat},{lon})[{f}];\n" for f in filters)
    query = f"[out:json][timeout:25];\n(\n{union});\nout center {cap};"

    last_err = "sem resposta"
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            resp = await client.post(
                endpoint, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=40
            )
            if resp.status_code != 200:
                last_err = f"{endpoint} → HTTP {resp.status_code}"
                continue
            elements = resp.json().get("elements", [])
            pois = [p for p in (_osm_to_poi(e, lat, lon) for e in elements) if p]
            # dedupe por (nome + coord arredondada) e ordena por proximidade
            seen: set[tuple] = set()
            uniq: list[dict] = []
            for p in sorted(pois, key=lambda x: x["dist_m"] if x["dist_m"] is not None else 1e9):
                k = (p["name"], round(p["lat"], 4), round(p["lon"], 4))
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(p)
            return uniq[:limit]
        except (httpx.HTTPError, ValueError) as exc:
            last_err = f"{endpoint} → {type(exc).__name__}: {exc}"
            continue
    raise ToolError(f"Overpass indisponível agora ({last_err}). Tente de novo em instantes.")


# ─────────────────────────── provider: OpenTripMap ─────────────────────────
async def _query_opentripmap(
    client: httpx.AsyncClient, lat: float, lon: float, radius_m: int, kinds: str, limit: int
) -> list[dict]:
    radius_params = {
        "radius": radius_m,
        "lon": lon,
        "lat": lat,
        "limit": min(limit, 50),
        "apikey": OPENTRIPMAP_API_KEY,
        "format": "json",
        "rate": 2,  # só POIs com alguma relevância
    }
    if kinds.strip():
        radius_params["kinds"] = kinds.strip()
    try:
        resp = await client.get(f"{OPENTRIPMAP_BASE}/radius", params=radius_params, timeout=20)
        resp.raise_for_status()
        features = resp.json()
    except httpx.HTTPStatusError as exc:
        raise ToolError(f"OpenTripMap recusou a busca (HTTP {exc.response.status_code}). Verifique a OPENTRIPMAP_API_KEY.")
    except httpx.HTTPError as exc:
        raise ToolError(f"OpenTripMap indisponível: {exc}")

    pois: list[dict] = []
    for feat in features[:limit]:
        xid = feat.get("xid")
        name = feat.get("name") or ""
        if not xid or not name:
            continue
        detail = {}
        try:
            d = await client.get(f"{OPENTRIPMAP_BASE}/xid/{xid}", params={"apikey": OPENTRIPMAP_API_KEY}, timeout=20)
            if d.status_code == 200:
                detail = d.json()
        except httpx.HTTPError:
            detail = {}  # detalhe é best-effort; segue com o básico do radius
        info = (detail.get("wikipedia_extracts") or {}).get("text") or (detail.get("info") or {}).get("descr") or ""
        point = detail.get("point") or {}
        pois.append(
            POI(
                id=xid,
                name=name or detail.get("name", ""),
                kind=feat.get("kinds") or detail.get("kinds", ""),
                lat=point.get("lat", lat),
                lon=point.get("lon", lon),
                dist_m=int(feat["dist"]) if feat.get("dist") is not None else None,
                preview=info[:280],
                wikidata=detail.get("wikidata"),
                source="opentripmap",
            ).model_dump()
        )
        await asyncio.sleep(0.12)  # respeita o rate-limit do free tier
    return pois


# ──────────────────────────────── a tool MCP ───────────────────────────────
@mcp.tool
async def poi_find(
    lat: float,
    lon: float,
    radius_m: int = 1500,
    kinds: str = "",
    limit: int = 10,
) -> list[dict]:
    """Busca pontos de interesse (POIs) REAIS perto de uma coordenada geográfica.

    Use esta ferramenta para listar atrações por dia/bairro de um roteiro: museus,
    parques, restaurantes, monumentos, miradouros etc. Não invente POIs — chame aqui.

    Args:
        lat: Latitude do ponto central (graus decimais, -90..90).
        lon: Longitude do ponto central (graus decimais, -180..180).
        radius_m: Raio de busca em metros (100..50000). Default 1500.
        kinds: Categorias separadas por vírgula. Vocabulário aceito (ex.):
            museums, cultural, restaurants, foods, cafes, bars, parks, gardens,
            natural, beaches, viewpoints, historic, monuments, architecture,
            religion, churches, hotels, shops, attractions, interesting_places.
            Vazio = mix de atrações + histórico + parques.
        limit: Máximo de POIs retornados (1..30). Default 10.

    Returns:
        Lista de POIs ordenada por proximidade. Cada POI:
        {id, name, kind, lat, lon, dist_m, preview, wikidata, source}.
    """
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ToolError("Coordenadas inválidas: lat deve estar em [-90,90] e lon em [-180,180].")
    radius_m = max(100, min(int(radius_m), 50_000))
    limit = max(1, min(int(limit), 30))

    key = _cache_key(lat, lon, radius_m, kinds, limit)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        if PROVIDER == "opentripmap":
            pois = await _query_opentripmap(client, lat, lon, radius_m, kinds, limit)
        else:
            pois = await _query_overpass(client, lat, lon, radius_m, kinds, limit)

    _cache_put(key, pois)
    return pois


if __name__ == "__main__":
    # stdio é o transporte default (usado pelo cliente MCP do agente LangChain).
    # `--http` sobe um endpoint streamable em http://127.0.0.1:8000/mcp para
    # inspeção manual (ex.: MCP Inspector / fastmcp dev).
    print(f"[poi-finder] provider ativo: {PROVIDER}", file=sys.stderr)
    if "--http" in sys.argv:
        mcp.run(transport="http", host="127.0.0.1", port=8000)
    else:
        mcp.run(show_banner=False)  # stdio: sem banner (mantém o protocolo limpo)
