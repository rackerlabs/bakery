from pathlib import Path


def _migration_filenames(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.glob("*.py") if path.name != "__init__.py")


def test_bakery_tracks_expected_alembic_migrations() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    bakery_versions = repo_root / "bakery/alembic/versions"

    assert _migration_filenames(bakery_versions) == [
        "001_initial_schema.py",
        "002_monitor_registry.py",
        "003_operator_control_plane.py",
    ]


def test_bakery_db_init_uses_standalone_alembic_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_init_source = (repo_root / "bakery/db_init.py").read_text(encoding="utf-8")

    assert 'Path("/app/bakery/alembic.ini")' in db_init_source
    assert 'Path(__file__).resolve().parent / "alembic.ini"' in db_init_source
    assert (
        'alembic_cfg.set_main_option("script_location", str(alembic_ini.parent / "alembic"))'
        in db_init_source
    )
