"""Map-specific Simplified Chinese callouts used by the review UI."""

from __future__ import annotations

import re
from typing import Any


MAP_DISPLAY_NAMES = {
    "de_ancient": "远古遗迹",
    "de_anubis": "阿努比斯",
    "de_cache": "死城之谜",
    "de_dust2": "炙热沙城 II",
    "de_inferno": "炼狱小镇",
    "de_mirage": "荒漠迷城",
    "de_nuke": "核子危机",
    "de_overpass": "死亡游乐园",
    "de_train": "列车停放站",
    "de_vertigo": "殒命大厦",
}


MAP_CALLOUTS: dict[str, dict[str, str]] = {
    "de_ancient": {
        "Alley": "外场小巷",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "House": "小屋",
        "MainHall": "A厅",
        "Middle": "中路",
        "Outside": "A外",
        "Ramp": "A斜坡",
        "Ruins": "遗迹",
        "SideEntrance": "侧入口",
        "SideHall": "侧厅",
        "TSideLower": "匪下",
        "TSideUpper": "匪上",
        "TSpawn": "匪家",
        "TopofMid": "中路上",
        "Tunnel": "隧道",
        "Water": "水区",
    },
    "de_anubis": {
        "Alley": "小巷",
        "BackofB": "B后",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "Bricks": "砖位",
        "Bridge": "桥",
        "CTSideUpper": "警上",
        "CTSpawn": "警家",
        "Canal": "水渠",
        "Connector": "B连接",
        "Fountain": "喷泉",
        "Heaven": "A2/天堂",
        "LowerTunnel": "下水道下层",
        "Main": "A外",
        "MidDoors": "中门",
        "Middle": "中路",
        "OutsideLong": "A外",
        "PalaceInterior": "宫殿内部",
        "Ruins": "废墟",
        "SnipersNest": "狙击位",
        "Street": "街道",
        "TSideUpper": "匪上",
        "TSpawn": "匪家",
        "TStairs": "匪楼梯",
        "Tunnel": "隧道",
        "TunnelStairs": "隧道楼梯",
        "Walkway": "步道",
        "Water": "水下",
    },
    "de_cache": {
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "TSpawn": "匪家",
        "Middle": "中路",
        "MidDoors": "中门",
        "Heaven": "A小",
        "Vents": "蓝门",
        "Garage": "蓝房",
        "Tunnel": "B厅",
        "Tunnels": "B厅",
        "Checkers": "B包",
    },
    "de_dust2": {
        "ARamp": "A大斜坡",
        "BDoors": "B门",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "Catwalk": "A小",
        "ExtendedA": "A大",
        "Hole": "B洞",
        "LongA": "A大",
        "LongDoors": "A门",
        "LowerTunnel": "B洞下层",
        "MidDoors": "中门",
        "Middle": "中路",
        "OutsideLong": "A门外",
        "OutsideTunnel": "B洞外",
        "Pit": "大坑",
        "ShortStairs": "A小楼梯",
        "Side": "中路侧道",
        "TRamp": "匪坡",
        "TSpawn": "匪家",
        "TopofMid": "中路",
        "TunnelStairs": "B洞楼梯",
        "UnderA": "A坑",
        "UpperTunnel": "B洞",
    },
    "de_inferno": {
        "Apartments": "二楼",
        "Arch": "拱门",
        "BackAlley": "后巷",
        "Balcony": "阳台",
        "Banana": "香蕉道",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "Bridge": "侧道桥",
        "CTSpawn": "警家",
        "Deck": "二楼",
        "Kitchen": "厨房",
        "Library": "书房",
        "LowerMid": "中楼下",
        "Middle": "中路",
        "Pit": "大坑",
        "Quad": "四箱",
        "Ruins": "废墟",
        "SecondMid": "二楼",
        "TRamp": "匪斜坡",
        "TSpawn": "匪家",
        "TopofMid": "中路上",
        "Underpass": "下水道",
        "Upstairs": "楼上",
    },
    "de_mirage": {
        "Apartments": "B二楼",
        "BackAlley": "匪后巷",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "Catwalk": "A小",
        "Connector": "拱门",
        "House": "小屋",
        "Jungle": "Jungle",
        "Ladder": "梯子",
        "Middle": "中路",
        "PalaceAlley": "A二楼外",
        "PalaceInterior": "A二楼",
        "Scaffolding": "脚手架",
        "Shop": "超市",
        "SideAlley": "侧巷",
        "SnipersNest": "狙位",
        "Stairs": "A楼梯",
        "TRamp": "匪斜坡",
        "TSpawn": "匪家",
        "TopofMid": "中路上",
        "Truck": "白车",
        "Underpass": "下水道",
    },
    "de_nuke": {
        "Admin": "办公室",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "Catwalk": "大仓",
        "Control": "控制室",
        "Crane": "起重机",
        "Decon": "消毒间",
        "Garage": "车库",
        "Heaven": "天堂",
        "Hell": "地狱",
        "Hut": "小房",
        "HutRoof": "小房顶",
        "Lobby": "大厅",
        "LockerRoom": "更衣室",
        "Mini": "迷你",
        "Observation": "观察室",
        "Outside": "外场",
        "Rafters": "横梁",
        "Ramp": "斜坡",
        "Roof": "屋顶",
        "Secret": "秘密通道",
        "Silo": "筒仓",
        "Squeaky": "吱吱门",
        "TSpawn": "匪家",
        "Trophy": "奖杯",
        "Tunnels": "隧道",
        "Vending": "自动售货机",
        "Vents": "管道",
    },
    "de_overpass": {
        "Alley": "小巷",
        "BackofA": "A后",
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "Bridge": "桥",
        "Canal": "下水道",
        "Connector": "连接",
        "Construction": "工地",
        "Fountain": "喷泉",
        "Lobby": "银行",
        "LowerPark": "下层游乐园",
        "Pipe": "管道",
        "Playground": "游乐园",
        "Restroom": "厕所",
        "SnipersNest": "狙位",
        "Stairs": "楼梯",
        "StorageRoom": "仓库",
        "TSpawn": "匪家",
        "TStairs": "匪楼梯",
        "Tunnels": "隧道",
        "UnderA": "A大坑",
        "UpperPark": "上层游乐园",
        "Walkway": "长管",
        "Water": "水下",
    },
    "de_train": {
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "TSpawn": "匪家",
        "Ivy": "绿通",
        "Popdog": "匪口",
        "Connector": "连接",
        "Heaven": "红楼梯",
    },
    "de_vertigo": {
        "BombsiteA": "A包",
        "BombsiteB": "B包",
        "CTSpawn": "警家",
        "TSpawn": "匪家",
        "Middle": "中路",
        "Ramp": "大坡",
        "Scaffolding": "脚手架",
        "Vents": "管道",
    },
}


def map_display_name(map_name: str | None) -> str:
    if not map_name:
        return "未知地图"
    return MAP_DISPLAY_NAMES.get(str(map_name), str(map_name))


def localize_place_name(map_name: str | None, place_name: str | None) -> str:
    if not place_name:
        return ""
    raw = str(place_name)
    return MAP_CALLOUTS.get(str(map_name or ""), {}).get(raw, raw)


def localize_text(map_name: str | None, value: str | None) -> str:
    if not value:
        return ""
    result = str(value)
    callouts = MAP_CALLOUTS.get(str(map_name or ""), {})
    for raw_name in sorted(callouts, key=len, reverse=True):
        replacement = callouts[raw_name]
        result = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(raw_name)}(?![A-Za-z0-9_])",
            replacement,
            result,
        )
    return result


def localize_fact_bundle_places(
    value: Any,
    map_name: str | None,
) -> Any:
    if isinstance(value, str):
        return localize_text(map_name, value)
    if isinstance(value, list):
        return [localize_fact_bundle_places(item, map_name) for item in value]
    if isinstance(value, dict):
        return {
            key: localize_fact_bundle_places(item, map_name)
            for key, item in value.items()
        }
    return value
