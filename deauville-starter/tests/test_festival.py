import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from festival.api import create_app
from festival.errors import Conflict, InvalidValue, NotFound, StorageError
from festival.models import Festival, Performance, make_slug
from festival.storage import FestivalRepository, JsonStorage

DATA_FILE = "data/festival.json"


def load_festival() -> Festival:
    return JsonStorage(Path(DATA_FILE)).load()


def test_loads_and_validates_seed_data() -> None:
    festival = load_festival()
    assert festival.name == "Deauville Festival du Rire 2027"
    assert len(festival.performances) == 23
    assert festival.get_performance("le-kiosque-2027-06-12-0100").festival_day == date(2027, 6, 11)


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Théâtre des Planches", "theatre-des-planches"), ("Élodie  Marchal !", "elodie-marchal")],
)
def test_slug(name: str, expected: str) -> None:
    assert make_slug(name) == expected


def test_artist_conflict_does_not_mutate_repository(tmp_path) -> None:
    source = load_festival()
    repository = FestivalRepository(JsonStorage(tmp_path / "festival.json"), source)
    repository.storage.save(source)
    original = source.to_dict()

    with pytest.raises(Conflict, match="busy"):
        repository.change(
            lambda festival: festival.add_performance(
                {
                    "kind": "solo",
                    "title": "Too soon",
                    "venue": "grand-casino",
                    "start": "2027-06-10T22:00",
                    "duration_minutes": 60,
                    "artist": "nora-lebrun",
                    "min_age": 0,
                }
            )
        )

    assert repository.festival.to_dict() == original
    assert JsonStorage(tmp_path / "festival.json").load().to_dict() == original


def test_workshop_registration_is_case_insensitive_and_persistent(tmp_path) -> None:
    source = load_festival()
    repository = FestivalRepository(JsonStorage(tmp_path / "festival.json"), source)
    repository.storage.save(source)
    workshop = next(show for show in source.performances if show.title == "Writing a Punchline")

    with pytest.raises(Conflict, match="already registered"):
        repository.change(lambda festival: festival.register_participant(workshop.id, " adam k. "))

    updated = repository.change(
        lambda festival: festival.register_participant(workshop.id, "  Camille P. ")
    )
    assert updated.participants[-1] == "Camille P."
    assert (
        JsonStorage(tmp_path / "festival.json").load().get_performance(workshop.id).participants[-1]
        == "Camille P."
    )


def test_invalid_lineup_duration_is_rejected() -> None:
    with pytest.raises(InvalidValue, match="at least 36 minutes"):
        Performance.from_dict(
            {
                "kind": "lineup",
                "title": "Short lineup",
                "venue": "le-kiosque",
                "start": "2027-06-11T20:00",
                "duration_minutes": 35,
                "host": "tom-vasseur",
                "acts": ["hugo-lemaire", "maya-choukri", "nora-lebrun"],
            }
        )


def test_unknown_reference_is_clear() -> None:
    festival = load_festival()
    original_count = len(festival.performances)
    with pytest.raises(NotFound, match="Unknown artist"):
        festival.add_performance(
            {
                "kind": "solo",
                "title": "Unknown artist show",
                "venue": "le-kiosque",
                "start": "2027-06-13T20:00",
                "duration_minutes": 30,
                "artist": "missing-artist",
                "min_age": 0,
            }
        )
    assert len(festival.performances) == original_count


def test_malformed_performance_kind_is_a_domain_error() -> None:
    with pytest.raises(InvalidValue, match="kind must be"):
        Performance.from_dict({"kind": [], "title": "Broken"})


def test_api_read_and_invalid_write(tmp_path) -> None:
    target = tmp_path / "festival.json"
    target.write_text(
        json.dumps(JsonStorage(Path(DATA_FILE)).load().to_dict()),
        encoding="utf-8",
    )
    client = TestClient(create_app(target))

    response = client.get("/api/programme", params={"day": "2027-06-11"})
    assert response.status_code == 200
    assert any(show["id"] == "le-kiosque-2027-06-12-0100" for show in response.json())
    assert client.get("/api/artists/not-here").status_code == 404
    assert client.get("/").status_code == 200
    assert client.get("/admin/").status_code == 200
    malformed_day = client.get("/api/programme", params={"day": "June 11"})
    assert malformed_day.status_code == 422
    assert isinstance(malformed_day.json()["detail"], list)
    malformed_moment = client.get("/api/now", params={"at": "June 11"})
    assert malformed_moment.status_code == 422
    assert isinstance(malformed_moment.json()["detail"], list)

    now = client.get("/api/now", params={"at": "2027-06-12T01:30"}).json()
    assert [show["title"] for show in now["now_playing"]] == ["After Hours"]

    created_artist = client.post(
        "/api/artists",
        json={"name": "  Alba   Noir ", "bio": "New comic."},
    )
    assert created_artist.status_code == 201
    assert created_artist.json()["slug"] == "alba-noir"
    persisted = JsonStorage(target).load()
    assert any(artist.name == "Alba   Noir" for artist in persisted.artists)

    invalid = client.post(
        "/api/performances",
        json={
            "kind": "solo",
            "title": "Invalid",
            "venue": "le-kiosque",
            "start": "2027-06-13T20:00",
            "duration_minutes": 500,
            "artist": "hugo-lemaire",
            "min_age": 0,
        },
    )
    assert invalid.status_code == 422


def test_broken_storage_has_clear_error(tmp_path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(StorageError, match="Cannot read festival data"):
        JsonStorage(path).load()
