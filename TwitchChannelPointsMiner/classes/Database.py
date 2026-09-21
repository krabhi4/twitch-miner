import json
import logging
import os
import time
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    Column,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

metadata = MetaData()

miner_config_table = Table(
    "miner_config",
    metadata,
    Column("username", String(255), primary_key=True),
    Column("config_data", Text, nullable=False),
    Column("updated_at", BigInteger, nullable=False),
)

streamer_series_table = Table(
    "streamer_series",
    metadata,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("username", String(255), nullable=False),
    Column("streamer", String(255), nullable=False),
    Column("x", BigInteger, nullable=False),
    Column("y", Integer, nullable=False),
    Column("z", String(100), nullable=False),
    Index("ix_series_user_streamer_x", "username", "streamer", "x"),
    Index("ix_series_user_streamer", "username", "streamer"),
)

streamer_annotations_table = Table(
    "streamer_annotations",
    metadata,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("username", String(255), nullable=False),
    Column("streamer", String(255), nullable=False),
    Column("x", BigInteger, nullable=False),
    Column("border_color", String(50), nullable=False),
    Column("text", Text, nullable=False),
    Column("data", Text, nullable=True),
    Index("ix_annotations_user_streamer_x", "username", "streamer", "x"),
    Index("ix_annotations_user_streamer", "username", "streamer"),
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()
    except Exception:
        pass


class DatabaseManager:
    def __init__(self, db_url=None, db_type=None, db_path=None):
        self.url = self._resolve_db_url(db_url, db_type, db_path)
        connect_args = {}
        if self.url.startswith("sqlite:"):
            connect_args["check_same_thread"] = False
        self.engine = create_engine(
            self.url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        metadata.create_all(self.engine)

    def _resolve_db_url(self, db_url=None, db_type=None, db_path=None):
        url = db_url or os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
        dtype = (
            db_type
            or os.environ.get("DATABASE_TYPE")
            or os.environ.get("DB_TYPE")
            or ""
        ).lower().strip()

        if url:
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://") :]
            return url

        if dtype in ("postgresql", "postgres"):
            raise ValueError(
                "PostgreSQL requested via DB_TYPE/DATABASE_TYPE, but DATABASE_URL/DB_URL is not set."
            )

        path = (
            db_path
            or os.environ.get("DATABASE_PATH")
            or os.environ.get("SQLITE_PATH")
        )
        if not path:
            analytics_base = Path("analytics").resolve()
            analytics_base.mkdir(parents=True, exist_ok=True)
            path = str(analytics_base / "miner.db")
        else:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            path = str(p)

        return f"sqlite:///{path}"

    def auto_migrate_json(self, username=None):
        search_dirs = []
        analytics_root = Path("analytics")
        if analytics_root.is_dir():
            search_dirs.append(analytics_root)
            for item in sorted(analytics_root.iterdir()):
                if (
                    item.is_dir()
                    and not item.name.startswith(".")
                    and item.name != "__pycache__"
                ):
                    search_dirs.append(item)

        for d in search_dirs:
            folder_user = d.name if d != analytics_root else (username or "")
            cfg_user = folder_user or username or "default"
            config_file = d / "config.json"
            if config_file.is_file():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f)
                    self.save_config(cfg_user, cfg_data)
                    config_file.unlink(missing_ok=True)
                    logger.info(
                        f"Migrated config.json for {cfg_user} to database and deleted file"
                    )
                except Exception as e:
                    logger.error(f"Failed to migrate {config_file}: {e}")

            for f in sorted(d.glob("*.json")):
                if f.name == "config.json":
                    continue
                streamer_name = f.stem.lower().strip()
                if (
                    not streamer_name
                    or streamer_name.startswith("change_me")
                    or streamer_name.startswith(".")
                ):
                    continue
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        streamer_data = json.load(file)
                except Exception as e:
                    logger.error(f"Failed to read {f} for migration: {e}")
                    continue

                target_user = folder_user or username
                if not target_user:
                    target_user = self.get_any_username() or "default"

                series_list = streamer_data.get("series", [])
                annotations_list = streamer_data.get("annotations", [])

                if series_list:
                    batch = []
                    for s in series_list:
                        batch.append(
                            {
                                "username": target_user,
                                "streamer": streamer_name,
                                "x": int(s.get("x", 0)),
                                "y": int(s.get("y", 0)),
                                "z": str(s.get("z", "Watch")),
                            }
                        )
                    self.bulk_insert_series(batch)

                if annotations_list:
                    batch = []
                    for a in annotations_list:
                        border_color = str(a.get("borderColor", ""))
                        text = str(
                            a.get("label", {}).get("text", "")
                            if isinstance(a.get("label"), dict)
                            else ""
                        )
                        batch.append(
                            {
                                "username": target_user,
                                "streamer": streamer_name,
                                "x": int(a.get("x", 0)),
                                "border_color": border_color,
                                "text": text,
                                "data": json.dumps(a),
                            }
                        )
                    self.bulk_insert_annotations(batch)

                f.unlink(missing_ok=True)
                (d / f"{f.name}.temp").unlink(missing_ok=True)
                (d / f"{f.name}.tmp").unlink(missing_ok=True)
                logger.info(
                    f"Migrated {len(series_list)} points and {len(annotations_list)} annotations "
                    f"for streamer '{streamer_name}' ({target_user}) to database and deleted {f.name}"
                )

    def bulk_insert_series(self, rows, chunk_size=1000):
        if not rows:
            return
        with self.engine.begin() as conn:
            for i in range(0, len(rows), chunk_size):
                conn.execute(insert(streamer_series_table), rows[i : i + chunk_size])

    def bulk_insert_annotations(self, rows, chunk_size=1000):
        if not rows:
            return
        with self.engine.begin() as conn:
            for i in range(0, len(rows), chunk_size):
                conn.execute(
                    insert(streamer_annotations_table),
                    rows[i : i + chunk_size],
                )

    def save_series(self, username, streamer, x, y, z):
        with self.engine.begin() as conn:
            conn.execute(
                insert(streamer_series_table).values(
                    username=username,
                    streamer=streamer.lower().strip(),
                    x=int(x),
                    y=int(y),
                    z=str(z),
                )
            )

    def save_annotation(self, username, streamer, x, border_color, text, data=None):
        data_str = json.dumps(data) if data is not None else None
        with self.engine.begin() as conn:
            conn.execute(
                insert(streamer_annotations_table).values(
                    username=username,
                    streamer=streamer.lower().strip(),
                    x=int(x),
                    border_color=str(border_color),
                    text=str(text),
                    data=data_str,
                )
            )

    def load_config(self, username):
        if not username:
            return None
        with self.engine.connect() as conn:
            stmt = select(miner_config_table.c.config_data).where(
                miner_config_table.c.username == username
            )
            row = conn.execute(stmt).fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except Exception:
                    return None
        return None

    def save_config(self, username, data):
        if not username or data is None:
            return
        data_str = json.dumps(data, indent=4)
        now = int(time.time())
        with self.engine.begin() as conn:
            check_stmt = select(miner_config_table.c.username).where(
                miner_config_table.c.username == username
            )
            exists = conn.execute(check_stmt).fetchone() is not None
            if exists:
                conn.execute(
                    update(miner_config_table)
                    .where(miner_config_table.c.username == username)
                    .values(config_data=data_str, updated_at=now)
                )
            else:
                conn.execute(
                    insert(miner_config_table).values(
                        username=username,
                        config_data=data_str,
                        updated_at=now,
                    )
                )

    def get_streamers(self, username):
        streamers = set()
        with self.engine.connect() as conn:
            stmt = (
                select(streamer_series_table.c.streamer)
                .where(streamer_series_table.c.username == username)
                .distinct()
            )
            for row in conn.execute(stmt):
                if row[0]:
                    streamers.add(row[0])
        cfg = self.load_config(username)
        if cfg and isinstance(cfg.get("streamers"), dict):
            for s in cfg["streamers"]:
                if s:
                    streamers.add(s.lower().strip())
        return sorted(list(streamers))

    def get_streamer_data(self, username, streamer, start_date=None, end_date=None):
        streamer = streamer.lower().strip()
        series = []
        annotations = []
        with self.engine.connect() as conn:
            s_stmt = select(
                streamer_series_table.c.x,
                streamer_series_table.c.y,
                streamer_series_table.c.z,
            ).where(
                streamer_series_table.c.username == username,
                streamer_series_table.c.streamer == streamer,
            )
            if start_date is not None and start_date > 0:
                s_stmt = s_stmt.where(streamer_series_table.c.x >= start_date)
            if end_date is not None and end_date > 0:
                s_stmt = s_stmt.where(streamer_series_table.c.x <= end_date)
            s_stmt = s_stmt.order_by(
                streamer_series_table.c.x.asc(),
                streamer_series_table.c.id.asc(),
            )

            for row in conn.execute(s_stmt):
                series.append({"x": row[0], "y": row[1], "z": row[2]})

            a_stmt = select(
                streamer_annotations_table.c.x,
                streamer_annotations_table.c.border_color,
                streamer_annotations_table.c.text,
                streamer_annotations_table.c.data,
            ).where(
                streamer_annotations_table.c.username == username,
                streamer_annotations_table.c.streamer == streamer,
            )
            if start_date is not None and start_date > 0:
                a_stmt = a_stmt.where(streamer_annotations_table.c.x >= start_date)
            if end_date is not None and end_date > 0:
                a_stmt = a_stmt.where(streamer_annotations_table.c.x <= end_date)
            a_stmt = a_stmt.order_by(
                streamer_annotations_table.c.x.asc(),
                streamer_annotations_table.c.id.asc(),
            )

            for row in conn.execute(a_stmt):
                if row[3]:
                    try:
                        parsed = json.loads(row[3])
                        annotations.append(parsed)
                        continue
                    except Exception:
                        pass
                color = row[1]
                annotations.append(
                    {
                        "borderColor": color,
                        "label": {
                            "style": {"color": "#000", "background": color},
                            "text": row[2],
                        },
                        "x": row[0],
                    }
                )

        return {"series": series, "annotations": annotations}

    def get_last_series_point(self, username, streamer):
        with self.engine.connect() as conn:
            stmt = (
                select(streamer_series_table.c.x, streamer_series_table.c.y)
                .where(
                    streamer_series_table.c.username == username,
                    streamer_series_table.c.streamer == streamer.lower().strip(),
                )
                .order_by(
                    streamer_series_table.c.x.desc(),
                    streamer_series_table.c.id.desc(),
                )
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if row:
                return {"x": row[0], "y": row[1]}
        return {"x": 0, "y": 0}

    def get_any_username(self):
        with self.engine.connect() as conn:
            stmt = select(miner_config_table.c.username).limit(1)
            row = conn.execute(stmt).fetchone()
            if row and row[0]:
                return row[0]
            stmt2 = select(streamer_series_table.c.username).limit(1)
            row2 = conn.execute(stmt2).fetchone()
            if row2 and row2[0]:
                return row2[0]
        return None

    def delete_streamer(self, username, streamer):
        streamer = streamer.lower().strip()
        with self.engine.begin() as conn:
            conn.execute(
                delete(streamer_series_table).where(
                    streamer_series_table.c.username == username,
                    streamer_series_table.c.streamer == streamer,
                )
            )
            conn.execute(
                delete(streamer_annotations_table).where(
                    streamer_annotations_table.c.username == username,
                    streamer_annotations_table.c.streamer == streamer,
                )
            )


_global_db_instance = None


def get_database(
    username=None, db_url=None, db_type=None, db_path=None
) -> DatabaseManager:
    global _global_db_instance
    if _global_db_instance is None:
        _global_db_instance = DatabaseManager(
            db_url=db_url, db_type=db_type, db_path=db_path
        )
    return _global_db_instance


def reset_database():
    global _global_db_instance
    _global_db_instance = None

