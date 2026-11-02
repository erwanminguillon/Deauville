import argparse
from datetime import date, datetime
from pathlib import Path

from festival.errors import FestivalError
from festival.models import parse_datetime
from festival.storage import JsonStorage

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "festival.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deauville Festival du Rire")
    commands = parser.add_subparsers(dest="command")
    day = commands.add_parser("day", help="Show a festival day's programme")
    day.add_argument("date", help="Festival day in YYYY-MM-DD format")
    commands.add_parser("artists", help="List artists and their show counts")
    now = commands.add_parser("now", help="Show what is on stage and what is next")
    now.add_argument(
        "--at",
        help="Local date and time in YYYY-MM-DDTHH:MM format (defaults to now)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        festival = JsonStorage(DATA_FILE).load()
        if args.command == "day":
            try:
                day = date.fromisoformat(args.date)
            except ValueError as exc:
                raise FestivalError("Day must use YYYY-MM-DD.") from exc
            if day.isoformat() != args.date or day not in festival.days:
                raise FestivalError("Choose a day within the festival dates.")
            shows = [show for show in festival.performances if show.festival_day == day]
            shows.sort(key=lambda show: (show.start, festival.get_venue(show.venue).name))
            for show in shows:
                print(
                    f"{show.start:%H:%M}  {show.title} — "
                    f"{festival.get_venue(show.venue).name} ({show.kind})"
                )
        elif args.command == "artists":
            for artist in sorted(festival.artists, key=lambda person: person.slug):
                count = sum(artist.slug in show.artist_slugs for show in festival.performances)
                print(f"{artist.name}: {count} show(s)")
        elif args.command == "now":
            moment = (
                parse_datetime(args.at)
                if args.at
                else datetime.now().replace(second=0, microsecond=0)
            )
            shows = sorted(
                festival.performances,
                key=lambda show: (show.start, festival.get_venue(show.venue).name),
            )
            current = [show for show in shows if show.start <= moment < show.end]
            upcoming = [show for show in shows if show.start > moment][:3]
            print(f"At {moment:%Y-%m-%d %H:%M}")
            print("On stage:")
            for show in current:
                print(f"  {show.title} — {festival.get_venue(show.venue).name}")
            print("Up next:")
            for show in upcoming:
                print(f"  {show.start:%Y-%m-%d %H:%M}  {show.title}")
        else:
            print(festival.name)
            build_parser().print_help()
    except (FestivalError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
