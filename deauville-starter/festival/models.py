from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Any

from festival.errors import Conflict, FestivalError, InvalidValue, NotFound


def make_slug(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    if not slug:
        raise InvalidValue("A name must contain at least one letter or digit.")
    return slug


def clean_name(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise InvalidValue(f"{label} must be text.")
    value = value.strip()
    if not value:
        raise InvalidValue(f"{label} cannot be empty.")
    return value


def parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise InvalidValue("Start must be a local date and time.")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise InvalidValue("Start must use YYYY-MM-DDTHH:MM local time.") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M") != value:
        raise InvalidValue("Start must use YYYY-MM-DDTHH:MM local time.")
    return parsed


@dataclass(frozen=True)
class Venue:
    name: str
    capacity: int
    address: str

    @property
    def slug(self) -> str:
        return make_slug(self.name)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "capacity": self.capacity, "address": self.address}


@dataclass(frozen=True)
class Artist:
    name: str
    bio: str = ""
    photo_url: str = ""

    @property
    def slug(self) -> str:
        return make_slug(self.name)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "bio": self.bio, "photo_url": self.photo_url}


@dataclass(frozen=True)
class Performance:
    kind: str
    title: str
    venue: str
    start: datetime
    duration_minutes: int
    description: str = ""
    artist: str | None = None
    min_age: int | None = None
    host: str | None = None
    acts: tuple[str, ...] = ()
    teacher: str | None = None
    max_participants: int | None = None
    participants: tuple[str, ...] = ()

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def id(self) -> str:
        return f"{self.venue}-{self.start:%Y-%m-%d-%H%M}"

    @property
    def festival_day(self) -> date:
        if self.start.time() < time(6):
            return self.start.date() - timedelta(days=1)
        return self.start.date()

    @property
    def artist_slugs(self) -> tuple[str, ...]:
        if self.kind == "solo":
            return (self.artist,) if self.artist else ()
        if self.kind == "lineup":
            return ((self.host,) if self.host else ()) + self.acts
        return (self.teacher,) if self.teacher else ()

    def to_dict(self) -> dict[str, Any]:
        common: dict[str, Any] = {
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue,
            "start": self.start.strftime("%Y-%m-%dT%H:%M"),
            "duration_minutes": self.duration_minutes,
            "description": self.description,
        }
        if self.kind == "solo":
            common.update(artist=self.artist, min_age=self.min_age)
        elif self.kind == "lineup":
            common.update(host=self.host, acts=list(self.acts))
        else:
            common.update(
                teacher=self.teacher,
                max_participants=self.max_participants,
                participants=list(self.participants),
            )
        return common

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Performance:
        if not isinstance(raw, dict):
            raise InvalidValue("Every performance must be an object.")
        kind = raw.get("kind")
        if not isinstance(kind, str) or kind not in {"solo", "lineup", "workshop"}:
            raise InvalidValue("Performance kind must be solo, lineup or workshop.")
        title = clean_name(raw.get("title"), "Performance title")
        venue = clean_name(raw.get("venue"), "Venue")
        start = parse_datetime(raw.get("start"))
        duration = raw.get("duration_minutes")
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise InvalidValue("Duration must be a whole number from 1 to 360 minutes.")
        if not 1 <= duration <= 360:
            raise InvalidValue("Duration must be from 1 to 360 minutes.")
        description = raw.get("description", "")
        if not isinstance(description, str):
            raise InvalidValue("Description must be text.")

        if kind == "solo":
            artist = clean_name(raw.get("artist"), "Artist")
            min_age = raw.get("min_age")
            if isinstance(min_age, bool) or not isinstance(min_age, int) or not 0 <= min_age <= 18:
                raise InvalidValue("Minimum age must be a whole number from 0 to 18.")
            return cls(
                kind, title, venue, start, duration, description, artist=artist, min_age=min_age
            )

        if kind == "lineup":
            host = clean_name(raw.get("host"), "Host")
            raw_acts = raw.get("acts")
            if not isinstance(raw_acts, list):
                raise InvalidValue("Acts must be a list of artist slugs.")
            acts = tuple(clean_name(act, "Act") for act in raw_acts)
            if len(acts) < 2:
                raise InvalidValue("A lineup must have at least two acts.")
            if len({make_slug(act) for act in acts}) != len(acts):
                raise InvalidValue("Each act can appear only once in a lineup.")
            if make_slug(host) in {make_slug(act) for act in acts}:
                raise InvalidValue("The host cannot also be an act.")
            minimum = len(acts) * 10 + (len(acts) - 1) * 3
            if duration < minimum:
                raise InvalidValue(
                    f"A lineup with {len(acts)} acts must last at least {minimum} minutes."
                )
            return cls(kind, title, venue, start, duration, description, host=host, acts=acts)

        teacher = clean_name(raw.get("teacher"), "Teacher")
        maximum = raw.get("max_participants")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise InvalidValue("A workshop must allow at least one participant.")
        raw_participants = raw.get("participants", [])
        if not isinstance(raw_participants, list):
            raise InvalidValue("Workshop participants must be a list of names.")
        participants = tuple(clean_name(name, "Participant name") for name in raw_participants)
        folded = [name.casefold() for name in participants]
        if len(set(folded)) != len(folded):
            raise InvalidValue("A participant can only register once.")
        return cls(
            kind,
            title,
            venue,
            start,
            duration,
            description,
            teacher=teacher,
            max_participants=maximum,
            participants=participants,
        )


class Festival:
    def __init__(
        self,
        name: str,
        first_day: date,
        last_day: date,
        venues: list[Venue],
        artists: list[Artist],
        performances: list[Performance],
    ) -> None:
        self.name = clean_name(name, "Festival name")
        self.first_day = first_day
        self.last_day = last_day
        self._venues = list(venues)
        self._artists = sorted(artists, key=lambda artist: artist.slug)
        self._performances = list(performances)
        self.validate()
        self._sort_performances()

    @property
    def venues(self) -> tuple[Venue, ...]:
        return tuple(self._venues)

    @property
    def artists(self) -> tuple[Artist, ...]:
        return tuple(self._artists)

    @property
    def performances(self) -> tuple[Performance, ...]:
        return tuple(self._performances)

    def _sort_performances(self) -> None:
        self._performances.sort(key=lambda show: (show.start, self.get_venue(show.venue).name))

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Festival:
        if not isinstance(raw, dict):
            raise InvalidValue("Festival data must be a JSON object.")
        try:
            first_day = date.fromisoformat(raw["first_day"])
            last_day = date.fromisoformat(raw["last_day"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidValue("Festival first_day and last_day must be valid dates.") from exc
        if not isinstance(raw.get("venues"), list) or not isinstance(raw.get("artists"), list):
            raise InvalidValue("Festival venues and artists must be lists.")
        if not isinstance(raw.get("performances"), list):
            raise InvalidValue("Festival performances must be a list.")

        venues: list[Venue] = []
        for item in raw["venues"]:
            if not isinstance(item, dict):
                raise InvalidValue("Every venue must be an object.")
            name = clean_name(item.get("name"), "Venue name")
            capacity = item.get("capacity")
            if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
                raise InvalidValue(f"{name} must have at least one seat.")
            address = item.get("address")
            if not isinstance(address, str):
                raise InvalidValue(f"{name} must have a text address.")
            venues.append(Venue(name, capacity, address.strip()))

        artists: list[Artist] = []
        for item in raw["artists"]:
            if not isinstance(item, dict):
                raise InvalidValue("Every artist must be an object.")
            name = clean_name(item.get("name"), "Artist name")
            bio, photo_url = item.get("bio", ""), item.get("photo_url", "")
            if not isinstance(bio, str) or not isinstance(photo_url, str):
                raise InvalidValue(f"{name}'s bio and photo URL must be text.")
            artists.append(Artist(name, bio, photo_url))
        performances = [Performance.from_dict(item) for item in raw["performances"]]
        return cls(
            clean_name(raw.get("name"), "Festival name"),
            first_day,
            last_day,
            venues,
            artists,
            performances,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [venue.to_dict() for venue in self.venues],
            "artists": [artist.to_dict() for artist in self.artists],
            "performances": [performance.to_dict() for performance in self.performances],
        }

    @property
    def days(self) -> list[date]:
        return [
            self.first_day + timedelta(days=offset)
            for offset in range((self.last_day - self.first_day).days + 1)
        ]

    def validate(self) -> None:
        if self.first_day > self.last_day:
            raise InvalidValue("Festival first_day must not be after last_day.")
        venue_slugs = [venue.slug for venue in self.venues]
        artist_slugs = [artist.slug for artist in self.artists]
        if len(set(venue_slugs)) != len(venue_slugs):
            raise Conflict("Two venues have the same name and slug.")
        if len(set(artist_slugs)) != len(artist_slugs):
            raise Conflict("Two artists have the same name and slug.")

        known_venues = set(venue_slugs)
        known_artists = set(artist_slugs)
        venue_by_slug = {venue.slug: venue for venue in self.venues}
        seen_ids: set[str] = set()
        for performance in self.performances:
            if performance.venue not in known_venues:
                raise NotFound(f"Unknown venue: {performance.venue}.")
            if performance.id in seen_ids:
                raise Conflict(
                    f"A performance already exists at {performance.start:%Y-%m-%d %H:%M}."
                )
            seen_ids.add(performance.id)
            if not self.first_day <= performance.festival_day <= self.last_day:
                raise Conflict(
                    f"{performance.title} is outside the festival dates "
                    f"({self.first_day} to {self.last_day})."
                )
            for slug in performance.artist_slugs:
                if slug not in known_artists:
                    raise NotFound(f"Unknown artist: {slug}.")
            if performance.kind == "workshop":
                capacity = min(
                    performance.max_participants or 0, venue_by_slug[performance.venue].capacity
                )
                if len(performance.participants) > capacity:
                    raise Conflict(
                        f"{performance.title} has more registrations than available places."
                    )
        self._validate_schedule(venue_by_slug)

    def _validate_schedule(self, venue_by_slug: dict[str, Venue]) -> None:
        venue_shows: dict[str, list[Performance]] = {}
        artist_shows: dict[str, list[Performance]] = {}
        for performance in self.performances:
            venue_shows.setdefault(performance.venue, []).append(performance)
            for slug in performance.artist_slugs:
                artist_shows.setdefault(slug, []).append(performance)

        for slug, shows in venue_shows.items():
            shows.sort(key=lambda show: show.start)
            venue = venue_by_slug[slug]
            for previous, following in pairwise(shows):
                if following.start < previous.end + timedelta(minutes=30):
                    raise Conflict(
                        f"{venue.name} is busy with {previous.title} "
                        f"({previous.start:%Y-%m-%d %H:%M}-{previous.end:%H:%M}). "
                        "Leave 30 minutes between two shows."
                    )
        for slug, shows in artist_shows.items():
            shows.sort(key=lambda show: show.start)
            artist = next(person for person in self.artists if person.slug == slug)
            for previous, following in pairwise(shows):
                if following.start < previous.end + timedelta(minutes=30):
                    raise Conflict(
                        f"{artist.name} is already in {previous.title} "
                        f"({previous.start:%Y-%m-%d %H:%M}-{previous.end:%H:%M}). "
                        "Leave 30 minutes between two performances."
                    )

    def get_artist(self, slug: str) -> Artist:
        for artist in self.artists:
            if artist.slug == slug:
                return artist
        raise NotFound(f"Unknown artist: {slug}.")

    def get_venue(self, slug: str) -> Venue:
        for venue in self.venues:
            if venue.slug == slug:
                return venue
        raise NotFound(f"Unknown venue: {slug}.")

    def get_performance(self, performance_id: str) -> Performance:
        for performance in self.performances:
            if performance.id == performance_id:
                return performance
        raise NotFound(f"Unknown performance: {performance_id}.")

    def add_artist(self, raw: dict[str, Any]) -> Artist:
        if not isinstance(raw, dict):
            raise InvalidValue("Artist data must be an object.")
        name = clean_name(raw.get("name"), "Artist name")
        artist = Artist(name, raw.get("bio", ""), raw.get("photo_url", ""))
        if not isinstance(artist.bio, str) or not isinstance(artist.photo_url, str):
            raise InvalidValue("Artist bio and photo URL must be text.")
        if any(existing.slug == artist.slug for existing in self.artists):
            raise Conflict(f"An artist named {artist.name} already exists.")
        self._artists.append(artist)
        self._artists.sort(key=lambda person: person.slug)
        return artist

    def add_performance(self, raw: dict[str, Any]) -> Performance:
        performance = Performance.from_dict(raw)
        self._performances.append(performance)
        try:
            self.validate()
        except FestivalError:
            self._performances.pop()
            raise
        self._sort_performances()
        return performance

    def replace_performance(self, performance_id: str, raw: dict[str, Any]) -> Performance:
        previous = self.get_performance(performance_id)
        performance = Performance.from_dict(raw)
        previous_index = self._performances.index(previous)
        self._performances[previous_index] = performance
        try:
            self.validate()
        except FestivalError:
            self._performances[previous_index] = previous
            raise
        self._sort_performances()
        return performance

    def remove_performance(self, performance_id: str) -> None:
        self._performances.remove(self.get_performance(performance_id))

    def register_participant(self, performance_id: str, name: str) -> Performance:
        performance = self.get_performance(performance_id)
        if performance.kind != "workshop":
            raise InvalidValue("Participants can only register for a workshop.")
        participant = clean_name(name, "Participant name")
        if any(
            existing.casefold() == participant.casefold() for existing in performance.participants
        ):
            raise Conflict(f"{participant} is already registered.")
        venue = self.get_venue(performance.venue)
        capacity = min(performance.max_participants or 0, venue.capacity)
        if len(performance.participants) >= capacity:
            raise Conflict(f"{performance.title} is full.")
        updated = Performance(
            performance.kind,
            performance.title,
            performance.venue,
            performance.start,
            performance.duration_minutes,
            performance.description,
            teacher=performance.teacher,
            max_participants=performance.max_participants,
            participants=performance.participants + (participant,),
        )
        self._performances[self._performances.index(performance)] = updated
        return updated
