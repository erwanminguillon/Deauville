from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from festival.errors import Conflict, FestivalError, InvalidValue, NotFound, StorageError
from festival.models import Artist, Festival, Performance, Venue, parse_datetime
from festival.storage import FestivalRepository, JsonStorage


def validate_local_datetime(value: str) -> str:
    try:
        parse_datetime(value)
    except InvalidValue as exc:
        raise ValueError(str(exc)) from exc
    return value


LocalDateTime = Annotated[str, AfterValidator(validate_local_datetime)]


class ArtistInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    bio: str = ""
    photo_url: str = ""


class PerformanceBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    venue: str
    start: LocalDateTime
    duration_minutes: int
    description: str = ""


class SoloInput(PerformanceBase):
    kind: Literal["solo"]
    artist: str
    min_age: int


class LineupInput(PerformanceBase):
    kind: Literal["lineup"]
    host: str
    acts: list[str]


class WorkshopInput(PerformanceBase):
    kind: Literal["workshop"]
    teacher: str
    max_participants: int
    participants: list[str] = Field(default_factory=list)


PerformanceInput = Annotated[
    SoloInput | LineupInput | WorkshopInput,
    Field(discriminator="kind"),
]


class ParticipantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "festival.json"


def artist_payload(artist: Artist) -> dict[str, str]:
    return {
        "slug": artist.slug,
        "name": artist.name,
        "bio": artist.bio,
        "photo_url": artist.photo_url,
    }


def venue_payload(venue: Venue) -> dict[str, object]:
    return {
        "slug": venue.slug,
        "name": venue.name,
        "capacity": venue.capacity,
        "address": venue.address,
    }


def performance_payload(festival: Festival, performance: Performance) -> dict[str, object]:
    venue = festival.get_venue(performance.venue)
    cast = [artist_payload(festival.get_artist(slug)) for slug in performance.artist_slugs]
    summary: str
    payload: dict[str, object] = {
        "id": performance.id,
        "kind": performance.kind,
        "title": performance.title,
        "venue": performance.venue,
        "venue_name": venue.name,
        "start": performance.start.strftime("%Y-%m-%dT%H:%M"),
        "end": performance.end.strftime("%Y-%m-%dT%H:%M"),
        "duration_minutes": performance.duration_minutes,
        "festival_day": performance.festival_day.isoformat(),
        "description": performance.description,
        "artists": [{"slug": artist["slug"], "name": artist["name"]} for artist in cast],
        "capacity": venue.capacity,
    }
    if performance.kind == "solo":
        payload.update(artist=performance.artist, min_age=performance.min_age)
        summary = f"with {cast[0]['name']}"
    elif performance.kind == "lineup":
        payload.update(host=performance.host, acts=list(performance.acts))
        summary = f"hosted by {cast[0]['name']}, with " + ", ".join(
            artist["name"] for artist in cast[1:]
        )
    else:
        capacity = min(performance.max_participants or 0, venue.capacity)
        payload.update(
            teacher=performance.teacher,
            max_participants=performance.max_participants,
            participants=list(performance.participants),
            capacity=capacity,
            places_left=capacity - len(performance.participants),
        )
        summary = f"workshop with {cast[0]['name']}"
    payload["summary"] = summary
    return payload


def create_app(data_file: Path = DATA_FILE) -> FastAPI:
    app = FastAPI(title="Deauville Festival du Rire API")
    storage = JsonStorage(data_file)
    try:
        repository: FestivalRepository | None = FestivalRepository(storage, storage.load())
        load_error: StorageError | None = None
    except StorageError as exc:
        repository = None
        load_error = exc

    def get_repository() -> FestivalRepository:
        if load_error is not None:
            raise load_error
        if repository is None:
            raise StorageError("Festival data is unavailable.")
        return repository

    @app.exception_handler(FestivalError)
    async def festival_error_handler(_request, exc: FestivalError) -> JSONResponse:
        if isinstance(exc, NotFound):
            status_code = 404
        elif isinstance(exc, Conflict):
            status_code = 409
        elif isinstance(exc, InvalidValue):
            status_code = 422
        else:
            status_code = 500
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    @app.get("/api/festival")
    def get_festival() -> dict[str, object]:
        festival = get_repository().festival
        return {
            "name": festival.name,
            "first_day": festival.first_day.isoformat(),
            "last_day": festival.last_day.isoformat(),
            "days": [day.isoformat() for day in festival.days],
        }

    @app.get("/api/venues")
    def get_venues() -> list[dict[str, object]]:
        return [venue_payload(venue) for venue in get_repository().festival.venues]

    @app.get("/api/artists")
    def get_artists() -> list[dict[str, str]]:
        return [
            artist_payload(artist)
            for artist in sorted(get_repository().festival.artists, key=lambda item: item.slug)
        ]

    @app.get("/api/artists/{slug}")
    def get_artist(slug: str) -> dict[str, object]:
        festival = get_repository().festival
        artist = festival.get_artist(slug)
        payload: dict[str, object] = artist_payload(artist)
        shows = [show for show in festival.performances if artist.slug in show.artist_slugs]
        shows.sort(key=lambda show: (show.start, festival.get_venue(show.venue).name))
        payload["performances"] = [performance_payload(festival, show) for show in shows]
        return payload

    @app.get("/api/programme")
    def get_programme(
        day: date | None = None,
        venue: str | None = None,
    ) -> list[dict[str, object]]:
        festival = get_repository().festival
        if venue is not None:
            festival.get_venue(venue)
        shows = [
            show
            for show in festival.performances
            if (day is None or show.festival_day == day) and (venue is None or show.venue == venue)
        ]
        shows.sort(key=lambda show: (show.start, festival.get_venue(show.venue).name))
        return [performance_payload(festival, show) for show in shows]

    @app.get("/api/performances/{performance_id}")
    def get_performance(performance_id: str) -> dict[str, object]:
        festival = get_repository().festival
        return performance_payload(festival, festival.get_performance(performance_id))

    @app.get("/api/now")
    def get_now(at: LocalDateTime | None = None) -> dict[str, object]:
        festival = get_repository().festival
        moment = (
            parse_datetime(at)
            if at is not None
            else datetime.now().replace(second=0, microsecond=0)
        )
        shows = sorted(
            festival.performances,
            key=lambda show: (show.start, festival.get_venue(show.venue).name),
        )
        current = [show for show in shows if show.start <= moment < show.end]
        upcoming = [show for show in shows if show.start > moment][:3]
        return {
            "at": moment.strftime("%Y-%m-%dT%H:%M"),
            "now_playing": [performance_payload(festival, show) for show in current],
            "up_next": [performance_payload(festival, show) for show in upcoming],
        }

    @app.post("/api/artists", status_code=201)
    def post_artist(body: ArtistInput) -> dict[str, str]:
        repo = get_repository()
        artist = repo.change(lambda festival: festival.add_artist(body.model_dump()))
        return artist_payload(artist)

    @app.post("/api/performances", status_code=201)
    def post_performance(body: PerformanceInput) -> dict[str, object]:
        repo = get_repository()
        performance = repo.change(lambda festival: festival.add_performance(body.model_dump()))
        return performance_payload(repo.festival, repo.festival.get_performance(performance.id))

    @app.put("/api/performances/{performance_id}")
    def put_performance(performance_id: str, body: PerformanceInput) -> dict[str, object]:
        repo = get_repository()
        performance = repo.change(
            lambda festival: festival.replace_performance(performance_id, body.model_dump())
        )
        return performance_payload(repo.festival, repo.festival.get_performance(performance.id))

    @app.delete("/api/performances/{performance_id}", status_code=204)
    def delete_performance(performance_id: str) -> None:
        get_repository().change(lambda festival: festival.remove_performance(performance_id))

    @app.post("/api/performances/{performance_id}/participants", status_code=201)
    def post_participant(performance_id: str, body: ParticipantInput) -> dict[str, object]:
        repo = get_repository()
        performance = repo.change(
            lambda festival: festival.register_participant(performance_id, body.name)
        )
        return performance_payload(repo.festival, repo.festival.get_performance(performance.id))

    app.mount("/admin", StaticFiles(directory=ROOT / "web" / "admin", html=True), name="admin")
    app.mount("/", StaticFiles(directory=ROOT / "web" / "public", html=True), name="public")
    return app


app = create_app()
