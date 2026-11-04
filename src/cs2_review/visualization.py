"""Plotly visualizations backed by the local SQLite fact store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import plotly.graph_objects as go
from PIL import Image

from cs2_review.map_callouts import localize_place_name

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP_DATA_VERSION = "2000940"
DEFAULT_MAP_ASSET_DIR = (
    PROJECT_ROOT / "assets" / "maps" / DEFAULT_MAP_DATA_VERSION
)


def _connect(database_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    return connection


def radar_coordinates(
    x: float,
    y: float,
    map_meta: dict[str, float],
) -> tuple[float, float]:
    scale = float(map_meta["scale"])
    return (
        (float(x) - float(map_meta["pos_x"])) / scale,
        (float(map_meta["pos_y"]) - float(y)) / scale,
    )


def load_map_asset(
    map_name: str,
    asset_dir: Path | str = DEFAULT_MAP_ASSET_DIR,
) -> tuple[Image.Image, dict[str, float]] | None:
    root = Path(asset_dir)
    radar_path = root / "radars" / f"{map_name}.png"
    map_data_path = root / "map_data.json"
    if not radar_path.is_file() or not map_data_path.is_file():
        return None
    map_data = json.loads(map_data_path.read_text(encoding="utf-8"))
    if map_name not in map_data:
        return None
    return Image.open(radar_path).convert("RGBA"), map_data[map_name]


def build_radar_figure(
    database_path: Path | str,
    *,
    analysis_id: str,
    steamid: str,
    map_name: str,
    round_num: int | None = None,
    height: int = 540,
    asset_dir: Path | str = DEFAULT_MAP_ASSET_DIR,
) -> go.Figure | None:
    asset = load_map_asset(map_name, asset_dir)
    if asset is None:
        return None
    image, metadata = asset

    params: list[Any] = [analysis_id, steamid]
    round_filter = ""
    if round_num is not None:
        round_filter = "AND round_num = ?"
        params.append(round_num)
    connection = _connect(database_path)
    try:
        rows = connection.execute(
            f"""
            SELECT round_num, tick, x, y, health, place_name
            FROM tick_sample
            WHERE analysis_id = ? AND steamid = ?
              AND x IS NOT NULL AND y IS NOT NULL
              {round_filter}
            ORDER BY round_num, tick
            """,
            params,
        ).fetchall()
    finally:
        connection.close()

    if not rows:
        return None

    width, height = image.size
    transformed = []
    for row in rows:
        radar_x, radar_y = radar_coordinates(row["x"], row["y"], metadata)
        if 0 <= radar_x <= width and 0 <= radar_y <= height:
            transformed.append((row, radar_x, radar_y))
    if not transformed:
        return None

    bins = 64
    hist, _, _ = np.histogram2d(
        [item[1] for item in transformed],
        [item[2] for item in transformed],
        bins=[bins, bins],
        range=[[0, width], [0, height]],
    )

    figure = go.Figure()
    figure.add_trace(
        go.Heatmap(
            z=hist.T,
            x=np.linspace(0, width, bins),
            y=np.linspace(0, height, bins),
            colorscale="Turbo",
            opacity=0.45,
            showscale=False,
            hoverinfo="skip",
        )
    )

    if round_num is None:
        for current_round in sorted({int(item[0]["round_num"]) for item in transformed}):
            points = [
                item for item in transformed
                if int(item[0]["round_num"]) == current_round
            ]
            figure.add_trace(
                go.Scatter(
                    x=[item[1] for item in points],
                    y=[item[2] for item in points],
                    mode="lines",
                    name=f"R{current_round}",
                    line={"width": 1.5},
                    opacity=0.7,
                    hoverinfo="skip",
                )
            )
    else:
        figure.add_trace(
            go.Scatter(
                x=[item[1] for item in transformed],
                y=[item[2] for item in transformed],
                mode="lines+markers",
                name=f"第 {round_num} 回合",
                line={"color": "#ffb000", "width": 2},
                marker={"size": 4},
                customdata=[
                    [
                        int(item[0]["tick"]),
                        localize_place_name(
                            map_name,
                            item[0]["place_name"],
                        ),
                        item[0]["health"],
                    ]
                    for item in transformed
                ],
                hovertemplate=(
                    "tick=%{customdata[0]}<br>"
                    "区域=%{customdata[1]}<br>"
                    "生命=%{customdata[2]}<extra></extra>"
                ),
            )
        )

    figure.add_layout_image(
        source=image,
        xref="x",
        yref="y",
        x=0,
        y=0,
        sizex=width,
        sizey=height,
        sizing="stretch",
        opacity=1.0,
        layer="below",
    )
    figure.update_xaxes(
        range=[0, width],
        visible=False,
        fixedrange=True,
    )
    figure.update_yaxes(
        range=[height, 0],
        visible=False,
        fixedrange=True,
        scaleanchor="x",
        scaleratio=1,
    )
    figure.update_layout(
        height=height,
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "y": 1.02},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#d7e0e7"},
        hoverlabel={"bgcolor": "#101a24", "font_color": "#f2f6f9"},
    )
    return figure


def build_economy_figure(
    database_path: Path | str,
    *,
    analysis_id: str,
) -> go.Figure:
    connection = _connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT round_num, side, equipment_value, buy_type
            FROM round_team_economy
            WHERE analysis_id = ?
            ORDER BY round_num, side
            """,
            (analysis_id,),
        ).fetchall()
    finally:
        connection.close()

    figure = go.Figure()
    labels = {
        "terrorist": "T",
        "counter-terrorist": "CT",
    }
    colors = {
        "terrorist": "#e5b14a",
        "counter-terrorist": "#5da9e9",
    }
    for side in ["terrorist", "counter-terrorist"]:
        side_rows = [row for row in rows if row["side"] == side]
        figure.add_trace(
            go.Bar(
                x=[int(row["round_num"]) for row in side_rows],
                y=[
                    float(row["equipment_value"]) / 1000.0
                    for row in side_rows
                ],
                name=labels[side],
                marker_color=colors[side],
                customdata=[
                    [row["buy_type"], row["equipment_value"]]
                    for row in side_rows
                ],
                hovertemplate=(
                    "回合 %{x}<br>%{customdata[0]}"
                    "<br>装备价值 %{customdata[1]}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        barmode="group",
        height=360,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        xaxis_title="回合",
        yaxis_title="队伍装备价值（千）",
        legend={"orientation": "h", "y": 1.08},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "#d7e0e7"},
        xaxis={"gridcolor": "rgba(145,162,178,0.14)"},
        yaxis={"gridcolor": "rgba(145,162,178,0.14)"},
        hoverlabel={"bgcolor": "#101a24", "font_color": "#f2f6f9"},
    )
    return figure

