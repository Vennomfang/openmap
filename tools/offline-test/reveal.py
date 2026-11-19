"""Explore to reveal (Options', the menu's; off unless chosen) in Lua 5.1: the map shows only what this
character has found. The whole addon is loaded as run.py loads it (its toc's files, less the client's
data), in a stubbed client with a small world of its own: one continent, two zones side by side with
explored-area pieces, a city, dungeons, docks and a boat between them, flight masters, townsfolk and two
painted gaps. The stitched map is built on it (Stitch.lua's S.Build) and the real option switched, so
what's checked is the addon's own code from the setting to the icons: which icons, routes, painted gaps
and search results show for what has been explored, that exploring brings them out, and that with the
option off nothing is hidden and nothing is looked up. (A stub: it can't see the art, nor what the game's
own frames and lookups do; docs/testing.md has the in-game check.) Then Stitch.lua's Shade.Over alone,
against every rectangle of random pieces. And the one-time setup question (Welcome.lua): every account
asked once, by a popup that only one of its two buttons answers. And the close-up minimap (Close.lua):
the world has the game's minimap tiles and its smaller copies, and every picture of it on screen is
looked at, at every zoom: with the option on, each must be cut to an explored piece and masked by that
piece's own art.
python -P tools/offline-test/reveal.py. Needs lupa."""
import json
import os
import random
import re
import unittest
from pathlib import Path

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "OpenMap"
STUB = Path(__file__).with_name("stub.lua")

# The small world. Azeroth (947) and one continent over all of it (1415: Stitch.lua's continent 0, whose
# corners place world yards); West (10) and East (20), each with pieces of its art (1002 x 668 px) to
# explore; a city in West (30: no pieces of its own, found with West's first piece, which lies under it).
# An area is a piece here: the ground in a piece's rectangle is explored once the piece is.
WORLD = r'''
Enum.UIMapType = { Cosmic = 0, World = 1, Continent = 2, Zone = 3, Dungeon = 4, Micro = 5, Orphan = 6 }
CreateVector2D = function(x, y) return { x = x, y = y, GetXY = function(self) return self.x, self.y end } end
QuestDifficultyColors = { difficult = { r = 1, g = 0.5, b = 0.25 } }
GetQuestDifficultyColor = function() return QuestDifficultyColors.difficult end
bit = { band = function(a, b) local r, p = 0, 1 while a > 0 and b > 0 do if a % 2 == 1 and b % 2 == 1 then r = r + p end a, b, p = math.floor(a / 2), math.floor(b / 2), p * 2 end return r end }
MAPS = {
	[947] = { name = "Azeroth", type = 1, rect = { 0, 1, 0, 1 }, art = 1 },
	[1415] = { name = "Continent", type = 2, parent = 947, rect = { 0, 1, 0, 1 }, art = 2 },
	[10] = { name = "West", type = 3, parent = 1415, rect = { 0.1, 0.5, 0.2, 0.8 }, art = 110 },
	[20] = { name = "East", type = 3, parent = 1415, rect = { 0.5, 0.9, 0.2, 0.8 }, art = 120 },
	[30] = { name = "City", type = 3, parent = 1415, rect = { 0.15, 0.2, 0.3, 0.4 }, art = 130 },
}
PIECES = {
	[110] = { ["200:200:100:100"] = "1101", ["200:200:600:300"] = "1102" },   -- West: its first piece (over the city), its second
	[120] = { ["300:300:300:200"] = "1201,1202,1203,1204" },                  -- East's (four tiles of 256)
}
explored = {}                   -- "<zone>:<piece>" -> true
here = 10                       -- the map the player is on
lookups, brokenLookups, noLookups = 0, false, false
farExplored = false             -- West's far corner explored: an area the map has no piece for
local function info(id) local m = MAPS[id] if m then return { mapID = id, name = m.name, mapType = m.type, parentMapID = m.parent } end end
local function rel(id, host)
	local a, h = MAPS[id] and MAPS[id].rect, MAPS[host] and MAPS[host].rect
	if not a or not h then return end
	local hw, hh = h[2] - h[1], h[4] - h[3]
	return (a[1] - h[1]) / hw, (a[2] - h[1]) / hw, (a[3] - h[3]) / hh, (a[4] - h[3]) / hh
end
C_Map = {
	GetMapInfo = info,
	GetMapArtID = function(id) return MAPS[id] and MAPS[id].art end,
	GetMapArtLayers = function(id)
		if MAPS[id] then return { { layerWidth = 1002, layerHeight = 668, tileWidth = 256, tileHeight = 256 } } end
	end,
	GetMapArtLayerTextures = function(id) local t = {} for i = 1, 12 do t[i] = id * 100 + i end return t end,
	GetMapRectOnMap = rel,
	GetMapChildrenInfo = function(id, kind)
		local out = {}
		for _, child in ipairs({ 1415, 10, 20, 30 }) do
			if MAPS[child].type == kind then out[#out + 1] = info(child) end
		end
		return out
	end,
	-- (the city first, as the game's continent map gives a city for any point in its rectangle)
	GetMapInfoAtPosition = function(id, x, y)
		for _, child in ipairs({ 1415, 30, 10, 20 }) do
			if MAPS[child].parent == id then
				local l, r, t, b = rel(child, id)
				if x >= l and x <= r and y >= t and y <= b then return info(child) end
			end
		end
	end,
	GetBestMapForUnit = function() return here end,
	-- (the continent's corners in yards: 16000 yards a side, 30 minimap tiles, x up the map and y across
	-- it, as the game's)
	GetWorldPosFromMapPos = function(id, pos)
		if id == 1415 then return 0, { x = (1 - pos.y) * 16000, y = (1 - pos.x) * 16000 } end
	end,
}
-- world yards (x, y) of a point on the world (normalized)
function Yards(u, v) return (1 - v) * 16000, (1 - u) * 16000 end
C_MapExplorationInfo = {
	GetExploredMapTextures = function(id)
		local out = {}
		for key, files in pairs(PIECES[MAPS[id] and MAPS[id].art or 0] or {}) do
			if explored[id .. ":" .. key] then
				local w, h, x, y = strsplit(":", key)
				out[#out + 1] = { textureWidth = tonumber(w), textureHeight = tonumber(h), offsetX = tonumber(x), offsetY = tonumber(y),
					fileDataIDs = { strsplit(",", files) }, isShownByMouseOver = false }
			end
		end
		return out
	end,
	GetExploredAreaIDsAtPosition = function(id, pos)
		lookups = lookups + 1
		if brokenLookups then error("the game can't say") end
		if noLookups then return nil end
		if id == 10 and farExplored and pos.x > 0.85 and pos.y > 0.85 then return { 2 } end
		local px, py = pos.x * 1002, pos.y * 668
		for key in pairs(PIECES[MAPS[id] and MAPS[id].art or 0] or {}) do
			local w, h, kx, ky = strsplit(":", key)
			w, h, kx, ky = tonumber(w), tonumber(h), tonumber(kx), tonumber(ky)
			if px >= kx and px <= kx + w and py >= ky and py <= ky + h and explored[id .. ":" .. key] then return { 1 } end
		end
		return {}
	end,
}
C_TaxiMap = { GetTaxiNodesForMap = function() return {} end }
-- the game's popups, as far as OpenMap's questions go: POPUPS[which] is the one up ({ which, text }); a
-- button calls what the game calls for it, and another popup pushing one out is its OnCancel, "override"
POPUPS, refusePopups = {}, false
function StaticPopup_Show(which, a1)
	local info = StaticPopupDialogs[which]
	if refusePopups or not info then return nil end
	local dialog = { which = which, text = info.text:format(a1) }
	POPUPS[which] = dialog
	return dialog
end
function StaticPopup_Visible(which) if POPUPS[which] then return which, POPUPS[which] end end
function StaticPopup_Hide(which) POPUPS[which] = nil end
function Press(which, button)
	local dialog, info = assert(POPUPS[which], which .. " isn't up"), StaticPopupDialogs[which]
	POPUPS[which] = nil
	if button == 1 then info.OnAccept(dialog, nil) else info.OnCancel(dialog, nil, "clicked") end
end
function PushOut(which)
	local dialog, info = assert(POPUPS[which], which .. " isn't up"), StaticPopupDialogs[which]
	POPUPS[which] = nil
	if info.OnCancel then info.OnCancel(dialog, nil, "override") end
end
-- timers a frame at a time (Frames), so what's done in one can be counted
QUEUE, WAIT = {}, nil            -- (WAIT: the seconds the timer last set was to wait)
C_Timer.After = function(seconds, fn) QUEUE[#QUEUE + 1], WAIT = fn, seconds end
function Frames(n)
	for _ = 1, n or 50 do
		local q = QUEUE
		if #q == 0 then return end
		QUEUE, NOW = {}, NOW + 0.016
		for _, fn in ipairs(q) do fn() end
	end
end

-- the game's minimap over all of it: a tile for each 533 yards (files from 9000000), and its two smaller
-- copies, 4 and 16 tiles a piece
MINI, LOD4, LOD16 = {}, {}, {}
for tx = 2, 31 do
	for ty = 2, 31 do MINI[tx * 64 + ty] = 9000000 + tx * 64 + ty end
end
for col = 0, 7 do
	for row = 0, 7 do LOD4[#LOD4 + 1] = col * 64 + row end
end
for col = 0, 1 do
	for row = 0, 1 do LOD16[#LOD16 + 1] = col * 64 + row end
end
-- what each texture was given (its file, its texcoords, its masks), kept on it for the tests to read
do
	local mt = getmetatable(UIParent)
	local index = mt.__index
	local kept = {
		SetTexture = function(self, file) rawset(self, "__file", file) return true end,
		SetTexCoord = function(self, ...) rawset(self, "__coords", { ... }) end,
		AddMaskTexture = function(self, mask)
			local masks = rawget(self, "__masks") or {}
			rawset(self, "__masks", masks)
			masks[#masks + 1] = mask
		end,
		RemoveMaskTexture = function(self, mask)
			local masks = rawget(self, "__masks") or {}
			for i = #masks, 1, -1 do if masks[i] == mask then table.remove(masks, i) end end
		end,
	}
	mt.__index = function(t, k) return kept[k] or index(t, k) end
end

local wx1, wy1 = Yards(0.38, 0.56)      -- West's dock, on its second piece
local wx2, wy2 = Yards(0.68, 0.47)      -- East's, on its piece
local fx1, fy1 = Yards(0.19, 0.41)      -- flight masters: West's camp, a post between, East's camp
local fx2, fy2 = Yards(0.45, 0.50)
local fx3, fy3 = Yards(0.70, 0.45)
local data = {
	MapReveal = PIECES,
	MapMinimap = { [0] = MINI },
	MapMinimapLOD = { [0] = { { 4, LOD4 }, { 16, LOD16 } } },
	-- a painted gap a piece of East's reaches into, and one with no piece near it
	MapGapFills = {
		{ "G01", { 0.70, 0.60, 0.80, 0.70 }, 256, 256, 1, { 1 } },
		{ "G02", { 0.92, 0.05, 0.98, 0.10 }, 256, 256, 1, { 1 } },
	},
	MapPlaces = {
		instances = {
			{ nil, 0.2, 0.3, { { 33, "Twin Keep", false, 20, 30 } }, map = 10 },    -- on West's first piece
			{ nil, 0.4, 0.4, { { 33, "Twin Keep", false, 20, 30 } }, map = 20 },    -- its other door, on East's piece
			{ nil, 0.5, 0.5, { { 35, "City Vault", false, 10, 20 } }, map = 30 },   -- in the city
			{ nil, 0.9, 0.9, { { 36, "Far Hold", false, 50, 60 } }, map = 10 },     -- on no piece: found by going in
		},
		transports = {
			{ "boat", "West - East", 0, wx1, wy1, 0, wx2, wy2 },
			{ "boat", "West - East", 0, wx2, wy2, 0, wx1, wy1 },
		},
		sailings = { { "boat", "West - East", { { 0, { wx1, wy1, wx2, wy2 } } } } },
	},
	MapFlights = {
		nodes = {
			[1] = { "West Camp, West", 0, fx1, fy1, 1 },
			[2] = { "Mid Post, West", 0, fx2, fy2, 1 },
			[3] = { "East Camp, East", 0, fx3, fy3, 1 },
			[4] = { "East Camp, East", 0, fx3 + 5, fy3 + 5, 2 },      -- the other faction's, of the same name
		},
		paths = {
			{ 1, 2, 300, 10, { fx1, fy1, fx2, fy2 } }, { 2, 1, 300, 10, { fx2, fy2, fx1, fy1 } },
			{ 2, 3, 300, 10, { fx2, fy2, fx3, fy3 } }, { 3, 2, 300, 10, { fx3, fy3, fx2, fy2 } },
		},
	},
}
for k, v in pairs(data) do ns[k] = v end
'''

# What the tests ask of the map, once it's built
HELPERS = r'''
mod, S = ns.modules.worldmap, ns.MapStitch
function Explore(zone, piece) explored[zone .. ":" .. piece] = true S.RefreshExplored() Frames() end
function Turn(on) mod.db.exploreReveal = on mod:Refresh() Frames() end
function Dungeon(name, nth)
	local n = 0
	for _, pin in ipairs(S.GetPinSet("dungeons").pins) do
		if pin.instances[1][2] == name then
			n = n + 1
			if n == (nth or 1) then return pin end
		end
	end
end
-- (the pins of one name in the tables' order: the entrances are made in it)
function Shown(name, nth) return Dungeon(name, nth):IsShown() end
function Docks()
	local out = {}
	for i, pin in ipairs(S.GetPinSet("boats").pins) do out[i] = pin:IsShown() end
	return out
end
function Flight(id)
	for _, pin in ipairs(S.GetPinSet("flight").pins) do if pin.node == id then return pin end end
end
function Fill(i) return S.fills[i][1]:IsShown() end
-- The close-up minimap. The view put on a point (Close.lua's S.SetView, as WorldMap.lua calls it on a pan
-- or zoom), `across` of the world wide, `steps` zoomed; and time passed (a picture comes in over a moment)
function Look(u, v, across, steps) S.SetView(u, v, across / 2, across / 2, steps, steps) end
function Wait(seconds) NOW = NOW + (seconds or 1) RunOnUpdate(0.016) end
-- a region's place on the world (normalized), as Stitch.lua anchored it
function Rect(r)
	local at = r.__points[1]
	if not at then return end
	local u0, v0 = at[4] / 1002, -at[5] / 668
	return u0, v0, u0 + r.__w / 1002, v0 + r.__h / 668
end
local function visible(r)
	while r do
		if rawget(r, "__shown") == false then return false end
		r = rawget(r, "__parent")
	end
	return true
end
local function minimap(file)
	return (type(file) == "number" and file >= 9000000) or (type(file) == "string" and file:find("MapMiniLOD", 1, true) ~= nil)
end
-- every picture of the minimap on screen now (a tile, a piece of a smaller copy, or a clip of one)
function Imagery()
	local out = {}
	for _, r in ipairs(FRAMES) do
		if r.__kind == "Texture" and minimap(rawget(r, "__file")) and visible(r) and (r.__alpha or 1) > 0 and r.__points[1] then
			out[#out + 1] = r
		end
	end
	return out
end
-- the explored pieces' tiles as the test has them: file -> { zone, piece, its place on the world, and its
-- file's whole place (256 px a file; at a piece's far edge, the next power of two past what's left) }
TILES = {}
local function pow2(n) local p = 16 while p < n do p = p * 2 end return p end
for zone, art in pairs({ [10] = 110, [20] = 120 }) do
	for key, files in pairs(PIECES[art]) do
		local w, h, x, y = strsplit(":", key)
		w, h, x, y = tonumber(w), tonumber(h), tonumber(x), tonumber(y)
		local m = MAPS[zone].rect
		local ku, kv = (m[2] - m[1]) / 1002, (m[4] - m[3]) / 668
		local cols = math.ceil(w / 256)
		for i, file in ipairs({ strsplit(",", files) }) do
			local col, row = (i - 1) % cols, math.floor((i - 1) / cols)
			local x0, y0 = x + col * 256, y + row * 256
			local pw, ph = math.min(256, x + w - x0), math.min(256, y + h - y0)
			TILES[tonumber(file)] = { zone = zone, piece = key,
				m[1] + x0 * ku, m[3] + y0 * kv, m[1] + (x0 + pw) * ku, m[3] + (y0 + ph) * kv,
				m[1] + (x0 + (pw < 256 and pow2(pw) or 256)) * ku, m[3] + (y0 + (ph < 256 and pow2(ph) or 256)) * kv }
		end
	end
end
-- the explored tile a picture is cut to and masked by, if it is: its whole rectangle inside the tile's,
-- the tile's own art laid over the tile as its mask
function CutTo(r)
	local u0, v0, u1, v1 = Rect(r)
	for _, mask in ipairs(rawget(r, "__masks") or {}) do
		local t = TILES[rawget(mask, "__file")]
		local m0, n0, m1, n1 = Rect(mask)
		if t and m0 and explored[t.zone .. ":" .. t.piece]
			and u0 >= t[1] - 1e-9 and v0 >= t[2] - 1e-9 and u1 <= t[3] + 1e-9 and v1 <= t[4] + 1e-9
			and math.abs(m0 - t[1]) < 1e-9 and math.abs(n0 - t[2]) < 1e-9 and math.abs(m1 - t[5]) < 1e-9 and math.abs(n1 - t[6]) < 1e-9 then
			return t
		end
	end
end
-- the pictures on screen not cut to explored land (none, with Explore to reveal), and how many are up
function Leaks()
	local leaks, shown = 0, Imagery()
	for _, r in ipairs(shown) do
		if not CutTo(r) then leaks = leaks + 1 end
	end
	return leaks, #shown
end
-- whether a picture of the minimap is up over a point of the world
function Over(u, v)
	for _, r in ipairs(Imagery()) do
		local u0, v0, u1, v1 = Rect(r)
		if u >= u0 and u <= u1 and v >= v0 and v <= v1 then return true end
	end
	return false
end
-- the views a test looks at: over each zone and the sea, from a zone's width down to a few tiles
VIEWS = {}
for _, at in ipairs({ { 0.19, 0.38 }, { 0.3, 0.5 }, { 0.42, 0.7 }, { 0.66, 0.44 }, { 0.8, 0.3 }, { 0.5, 0.5 }, { 0.05, 0.9 } }) do
	for _, across in ipairs({ 0.9, 0.5, 0.3, 0.12, 0.05 }) do VIEWS[#VIEWS + 1] = { at[1], at[2], across } end
end
function Route() return (S.GetPinSet("routes").frame:GetChildren()):IsShown() end
function Folk(name)
	for _, pin in ipairs(S.GetPinSet("tf_vendor").pins) do if pin.data.name == name then return pin:IsShown() end end
	error("no pin for " .. name)
end
-- a database in Questie's shape (Townsfolk.lua's provider): vendors at places on the zones' maps (0..100);
-- `frames`: how many frames of building them to run (all of it, unless given)
function Vendors(list, frames)
	local npcs = {}
	for i, v in ipairs(list) do
		npcs[i] = { name = v[1], npcFlags = 1, friendlyToFaction = "AH", spawns = { [v[2]] = { { v[3], v[4] } } } }
	end
	mod.db.townsfolk.vendor = true
	mod.SetTownsfolkProvider({
		db = { npcFlags = { VENDOR = 1 }, NPCPointers = npcs, QueryNPCSingle = function(id, field) return npcs[id][field] end },
		zones = { GetUiMapIdByAreaId = function(_, area) return area end },
	})
	Frames(frames)
end
local function upvalue(fn, wanted)
	for i = 1, 200 do
		local name, value = debug.getupvalue(fn, i)
		if name == wanted then return value end
		if not name then break end
	end
	error("no " .. wanted)
end
-- Nav.lua's search: the names found for a text, each with its place ("name@u,v": to 2 decimals)
function Search(text)
	local Results = upvalue(upvalue(mod.CreateSearch, "ShowResults"), "Results")
	local out = {}
	for _, r in ipairs(Results(text)) do
		out[#out + 1] = ("%s@%.2f,%.2f"):format(r[1].name, r[1][1], r[1][2])
	end
	table.sort(out)
	return table.concat(out, "; ")
end
-- the menu's rows (Panel.lua's), by id
function Rows()
	local out = {}
	for _, row in ipairs(upvalue(upvalue(mod.RefreshPanel, "Fill"), "Rows")()) do
		if row.id then out[row.id] = row end
	end
	return out
end
'''


def toc_files():
    """WoW Forever's toc's files, as run.py reads them, less its data (the small world's own stand in)"""
    def expand(rel):
        if not rel.endswith(".xml"):
            return [rel]
        base = os.path.dirname(rel)
        text = re.sub(r"<!--.*?-->", "", (ADDON / rel).read_text(encoding="utf-8"), flags=re.S)
        out = []
        for m in re.finditer(r'<(Script|Include)\s+file="([^"]+)"', text):
            out.extend(expand(os.path.join(base, m.group(2).replace("\\", os.sep)).replace(os.sep, "/")))
        return out
    out = []
    for line in (ADDON / "OpenMap.toc").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        while re.search(r"\s*\[[^\]]*\]\s*$", line):
            line = re.sub(r"\s*\[[^\]]*\]\s*$", "", line)
        rel = line.replace("\\", "/")
        if rel.startswith("Data/") and not rel.endswith("Client.lua"):
            continue
        out.extend(expand(rel))
    return out


def world(reveal=False, saved=None):
    """the addon loaded and the stitched map built on the small world (Explore to reveal as saved: `reveal`;
    `saved`: the account's saved settings as Lua, for the one-time setup question's tests)"""
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUB.read_text(encoding="utf-8"))
    lua.execute("ns = {}")
    load = lua.eval(r"""function(src, name)
        local fn, err = loadstring(src, "@" .. name)
        if not fn then error(err) end
        fn("OpenMap", ns)
    end""")
    for rel in toc_files():
        if rel == "Map/Stitch.lua":
            lua.execute(WORLD)              # (the world and its data, before the map's own files)
        load((ADDON / rel).read_text(encoding="utf-8-sig"), rel)
    if reveal:
        lua.execute("OpenMapDB = { worldmap = { exploreReveal = true } }")
    if saved is not None:
        lua.execute("OpenMapDB = " + saved)
    lua.execute("""
        FireEvent("ADDON_LOADED", "OpenMap")
        FireEvent("PLAYER_LOGIN")
        FireEvent("PLAYER_ENTERING_WORLD", true, false)
        Frames()
    """)
    lua.execute(HELPERS)
    lua.execute("""
        mod.db.routes = true
        mod.char.flightsKnown = { ["West Camp, West"] = true }      -- (learned at a flight master: West's camp alone)
        -- (as WorldMap.lua builds it: the art, what's built on it, then a refresh)
        assert(S.Build(CreateFrame("Frame"), 100, 80, 2000), "the stitched map built")
        mod:BuildFlights()
        mod:Refresh()
        Frames()
        S.Cull(0, 0, 1, 1)
    """)
    return lua


class Case(unittest.TestCase):
    reveal = False

    def setUp(self):
        self.lua = world(self.reveal)

    def tearDown(self):
        errs = self.lua.eval("ERRORS")
        self.assertEqual([errs[i] for i in range(1, len(errs) + 1)], [], "Lua errors while it ran")

    def run_lua(self, code):
        self.lua.execute(code)

    def get(self, expr):
        return self.lua.eval(expr)


class OffTests(Case):
    """off (as it comes): the map as it was, and nothing looked up for it"""

    def test_off_by_default_and_nothing_hidden(self):
        self.run_lua("""
            assert(mod.db.exploreReveal == false and not mod.ExploreReveal(), "off by default")
            assert(mod.Unexplored() == "show" and not mod.FoundOnly(), "the two settings it stands in for, as they come")
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor Far", 10, 90, 90 } })
            for _, name in ipairs({ "Twin Keep", "City Vault", "Far Hold" }) do assert(Shown(name), name) end
            assert(Shown("Twin Keep", 2))
            for _, shown in ipairs(Docks()) do assert(shown, "a dock") end
            for id = 1, 3 do assert(Flight(id):IsShown(), "flight master " .. id) end
            assert(Fill(1) and Fill(2), "the painted gaps")
            assert(Route(), "the boat's route")
            assert(Folk("Vendor West") and Folk("Vendor Far"), "the townsfolk")
            assert(Search("twin") == "Twin Keep@0.18,0.38" and Search("camp"):find("East Camp, East", 1, true), "the search")
        """)

    def test_off_looks_nothing_up(self):
        # (the game is asked what's explored at a place only for the cities, as before: S.RefreshExplored's
        # own check of each unfound one, and never by a refresh)
        self.run_lua("""
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor East", 20, 40, 40 }, { "Vendor Far", 10, 90, 90 } })
            local before = lookups
            for _ = 1, 3 do mod:Refresh() Frames() end
            -- (asked as Stitch.lua asks when what's found changes: no pass over the pins, not even one that finds nothing to do)
            local waiting = #QUEUE
            S.RefreshFolk(true) S.RefreshFolk()
            assert(#QUEUE == waiting, "the townsfolk's pins gone over with the option off")
            S.RefreshRoutes(true) Frames()
            assert(lookups == before, "a refresh looked " .. (lookups - before) .. " places up with the option off")
            Explore(20, "300:300:300:200")
            assert(lookups - before <= 1, "exploring looked " .. (lookups - before) .. " places up with the option off")
            assert(Folk("Vendor West") and Folk("Vendor East") and Folk("Vendor Far"))
        """)

    def test_the_settings_it_stands_in_for_still_work_alone(self):
        self.run_lua("""
            mod.db.foundOnly = true
            mod:Refresh() Frames()
            assert(not Shown("Twin Keep") and not Flight(2):IsShown() and Flight(1):IsShown(), "Only places you've found, alone")
            assert(Fill(1) and Route(), "... leaves the painted gaps and the routes, as before")
            assert(Search("twin") ~= "", "... and the search")
            mod.db.foundOnly = false
            mod.SetUnexplored("hide")
            assert(mod.Unexplored() == "hide" and Shown("Twin Keep") and Fill(1), "Unexplored areas: Hide, alone")
        """)


class OnTests(Case):
    """on: only what's found"""

    def test_hides_what_isnt_found(self):
        self.run_lua("""
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor East", 20, 40, 40 }, { "Vendor City", 30, 50, 50 }, { "Vendor Far", 10, 90, 90 } })
            Turn(true)
            assert(mod.ExploreReveal() and mod.Unexplored() == "hide" and mod.FoundOnly(), "unexplored areas hidden, only the places found")
            for _, name in ipairs({ "Twin Keep", "City Vault", "Far Hold" }) do assert(not Shown(name), name) end
            assert(not Shown("Twin Keep", 2))
            for _, shown in ipairs(Docks()) do assert(not shown, "a dock") end
            assert(Flight(1):IsShown() and not Flight(2):IsShown() and not Flight(3):IsShown(), "flight masters: the learned one")
            assert(not Fill(1), "the painted gap East's unexplored piece reaches")
            assert(Fill(2), "... and the one with no piece near it, which nothing can find: shown")
            assert(not Route(), "the route with neither dock found")
            for _, name in ipairs({ "Vendor West", "Vendor East", "Vendor City", "Vendor Far" }) do assert(not Folk(name), name) end
        """)

    def test_exploring_brings_them_out(self):
        self.run_lua("""
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor East", 20, 40, 40 }, { "Vendor City", 30, 50, 50 }, { "Vendor Far", 10, 90, 90 } })
            Turn(true)
            Explore(20, "300:300:300:200")           -- East's piece
            assert(Shown("Twin Keep", 2) and not Shown("Twin Keep", 1), "the door on the piece explored, not the other")
            assert(Fill(1), "the painted gap beside it")
            assert(Route(), "the route, its East dock found")
            local docks = Docks()
            assert(docks[1] ~= docks[2], "the East dock, not West's")
            assert(Folk("Vendor East") and not Folk("Vendor West") and not Folk("Vendor City") and not Folk("Vendor Far"))
            assert(not Flight(3):IsShown(), "a flight master isn't found by exploring: learned")
            Explore(10, "200:200:100:100")           -- West's first, with the city under it
            assert(Shown("Twin Keep", 1) and Shown("City Vault"), "West's door, and the city's with the city")
            assert(Folk("Vendor West") and Folk("Vendor City") and not Folk("Vendor Far"))
            assert(not Shown("Far Hold"), "on no piece: not by exploring")
        """)

    def test_a_dungeon_youve_been_in_and_a_city_youve_walked_into(self):
        self.run_lua("""
            Vendors({ { "Vendor City", 30, 50, 50 } })
            Turn(true)
            mod.char.entered = { [36] = true }       -- (Dungeons.lua's, as you go in)
            S.RefreshFound() Frames()
            assert(Shown("Far Hold"), "a dungeon you've been inside")
            here = 30                                -- into the city by its gate, West's piece over it unexplored
            S.RefreshCities() Frames()
            assert(Shown("City Vault") and Folk("Vendor City"), "what's in a city, found with the city")
        """)

    def test_an_area_with_no_piece_of_its_own(self):
        # (the game says somewhere was explored, and no piece of the map changed: looked at again all the same)
        self.run_lua("""
            Vendors({ { "Vendor Far", 10, 90, 90 } })
            Turn(true)
            assert(not Shown("Far Hold") and not Folk("Vendor Far"))
            farExplored = true
            S.RefreshExplored() Frames()             -- (MAP_EXPLORATION_UPDATED)
            assert(Shown("Far Hold") and Folk("Vendor Far"), "found by the game's own word for the ground there")
        """)

    def test_off_again_all_back_and_the_settings_as_they_were(self):
        self.run_lua("""
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor Far", 10, 90, 90 } })
            mod.db.unexplored = "dim"
            Turn(true)
            assert(mod.Unexplored() == "hide" and mod.db.unexplored == "dim" and mod.db.foundOnly == false, "theirs kept")
            mod.SetUnexplored("show")                -- (set while it's on: kept for after, not acted on)
            assert(mod.Unexplored() == "hide")
            Turn(false)
            assert(mod.Unexplored() == "show" and not mod.FoundOnly())
            for _, name in ipairs({ "Twin Keep", "City Vault", "Far Hold" }) do assert(Shown(name), name) end
            for _, shown in ipairs(Docks()) do assert(shown, "a dock") end
            for id = 1, 3 do assert(Flight(id):IsShown(), "flight master " .. id) end
            assert(Fill(1) and Fill(2) and Route() and Folk("Vendor West") and Folk("Vendor Far"))
        """)

    def test_a_painted_gap_stays_hidden_through_a_pan(self):
        # (S.Cull shows what's near the view: not a painted gap still to be found)
        self.run_lua("""
            Turn(true)
            S.Cull(0, 0, 0.2, 0.2)                   -- the view elsewhere: both off it
            assert(not Fill(1) and not Fill(2))
            S.Cull(0, 0, 1, 1)                       -- and back
            assert(not Fill(1) and Fill(2), "back in view: the one not found still hidden")
            S.Cull(0, 0, 0.2, 0.2)
            Explore(20, "300:300:300:200")           -- found while off the view: not shown there
            assert(not Fill(1))
            S.Cull(0, 0, 1, 1)
            assert(Fill(1), "... and shown once it's back in view")
        """)

    def test_the_search_finds_only_what_youve_found(self):
        self.run_lua("""
            Turn(true)
            assert(Search("twin") == "" and Search("vault") == "" and Search("hold") == "", "no dungeon you haven't found")
            assert(Search("camp") == "West Camp, West@0.19,0.41", "flight masters: the learned one: " .. Search("camp"))
            assert(Search("post") == "", "... not one you haven't learned")
            assert(Search("west"):find("West@", 1, true) and Search("city") == "City@0.15,0.30", "zones always, as the game's map names them")
            Explore(20, "300:300:300:200")
            -- (the dungeon by its second door, the one found: there, not at the first)
            assert(Search("twin") == "Twin Keep@0.66,0.44", Search("twin"))
            Explore(10, "200:200:100:100")
            assert(Search("twin") == "Twin Keep@0.18,0.38" and Search("vault") ~= "")
            mod.char.flightsKnown["East Camp, East"] = true
            assert(Search("east camp"):find("East Camp, East@", 1, true), "learned: found")
            Turn(false)
            assert(Search("post") ~= "" and Search("hold") ~= "", "off: every place")
        """)

    def test_a_flight_route_keeps_to_flight_masters_youve_learned(self):
        self.run_lua("""
            mod.char.flightsKnown["East Camp, East"] = true
            mod.RefreshFlightsFound()
            local route = S.GetPinSet("route")
            -- off: West's camp to East's goes by the post between, not learned, and says so
            Flight(1).OnClick(Flight(1)) Flight(3).OnClick(Flight(3))
            assert(#route.lines > 0, "off: the route by a flight master not learned")
            Turn(true)
            assert(#route.lines == 0, "turned on: that route goes")
            assert(Flight(1):IsShown() and Flight(3):IsShown() and not Flight(2):IsShown())
            local said = #LOG
            Flight(1).OnClick(Flight(1)) Flight(3).OnClick(Flight(3))
            assert(#route.lines == 0, "on: no route through one you haven't learned")
            assert(#LOG == said + 1 and LOG[#LOG]:find("No flight route", 1, true), "... and it says there's none")
            mod.char.flightsKnown["Mid Post, West"] = true
            mod.RefreshFlightsFound()
            Flight(1).OnClick(Flight(1)) Flight(3).OnClick(Flight(3))
            assert(#route.lines > 0, "learned: the route")
        """)

    def test_where_the_game_cant_say(self):
        self.run_lua("""
            Vendors({ { "Vendor West", 10, 20, 30 } })
            -- an error from the game's lookup: shown, not lost for good
            brokenLookups = true
            assert(S.FoundIn(10, 0.2, 0.3) == true)
            brokenLookups = false
            -- nothing back (an instance, a map with no areas): not found
            noLookups = true
            assert(S.FoundIn(10, 0.2, 0.3) == false)
            noLookups = false
            -- a map with no pieces to explore is never hidden: its icons neither
            local before = lookups
            assert(S.FoundIn(999, 0.5, 0.5) == true and lookups == before)
            -- the city: as the city is found, whatever its own map says
            assert(S.FoundIn(30, 0.5, 0.5) == false)
            Explore(10, "200:200:100:100")
            assert(S.FoundIn(30, 0.5, 0.5) == true and S.FoundIn(10, 0.2, 0.3) == true and S.FoundIn(10, 0.9, 0.9) == false)
        """)

    def test_townsfolk_a_few_hundred_a_frame(self):
        self.run_lua("""
            local list = {}
            for i = 1, 1000 do list[i] = { "Vendor " .. i, 10, 20 + (i % 7), 30 } end
            Vendors(list)
            local pins = S.GetPinSet("tf_vendor").pins
            assert(#pins == 1000)
            local before = lookups
            mod.db.exploreReveal = true
            mod:Refresh()
            local own = lookups - before            -- (the places' own icons, looked up as the option is set)
            local most, frames = 0, 0
            while #QUEUE > 0 do
                local at = lookups
                Frames(1)
                most, frames = math.max(most, lookups - at), frames + 1
            end
            -- (300 a frame, Townsfolk.lua's FOUND_STEP, from the frame after)
            assert(own < 100 and most == 300, "a frame looked " .. most .. " places up, the refresh itself " .. own)
            assert(frames == 4 and lookups - before - own == 1000, "every pin looked up once, over " .. frames .. " frames")
            for _, pin in ipairs(pins) do assert(not pin:IsShown()) end
            -- nothing changed: a refresh (another setting) looks none of them up again
            before = lookups
            mod:RefreshTownsfolk() Frames()
            assert(lookups == before, "looked up again with nothing changed")
            -- explored: again, and found; and found ones are never looked up after that
            Explore(10, "200:200:100:100")
            for _, pin in ipairs(pins) do assert(pin:IsShown()) end
            before = lookups
            Explore(10, "200:200:600:300")
            assert(lookups - before < 100, "pins found already were looked up again: " .. (lookups - before))
        """)

    def test_townsfolk_hidden_from_the_frame_theyre_made(self):
        # (a database is gone through over several frames: a pin made in the first isn't shown until the last)
        self.run_lua("""
            Turn(true)
            local list = {}
            for i = 1, 1000 do list[i] = { "Vendor " .. i, 10, 20, 30 } end
            Vendors(list, 0)                         -- (its first few hundred, no frame run yet)
            local pins = S.GetPinSet("tf_vendor").pins
            assert(#pins >= 300 and #pins < 1000, #pins .. " made in the first frame")
            for _, pin in ipairs(pins) do assert(not pin:IsShown(), "shown before it was looked up") end
            Frames()
            assert(#pins == 1000)
            for _, pin in ipairs(pins) do assert(not pin:IsShown()) end
        """)

    def test_a_kind_turned_on_later(self):
        self.run_lua("""
            Turn(true)
            Explore(20, "300:300:300:200")
            Vendors({ { "Vendor West", 10, 20, 30 }, { "Vendor East", 20, 40, 40 } })   -- (made with the option on)
            assert(Folk("Vendor East") and not Folk("Vendor West"), "looked up as they're made")
            mod.db.townsfolk.vendor = false
            mod:RefreshTownsfolk() Frames()
            Explore(10, "200:200:100:100")           -- explored while the kind is off: not looked up for it
            mod.db.townsfolk.vendor = true
            mod:RefreshTownsfolk() Frames()
            assert(Folk("Vendor West"), "turned on again: as explored by now")
        """)


class SavedOnTests(Case):
    """saved on: as the map is built at login"""
    reveal = True

    def test_on_from_login(self):
        self.run_lua("""
            assert(mod.ExploreReveal() and mod.Unexplored() == "hide")
            assert(not Shown("Twin Keep") and not Fill(1) and Fill(2) and not Route())
            assert(Flight(1):IsShown() and not Flight(2):IsShown())
            Explore(20, "300:300:300:200")
            assert(Shown("Twin Keep", 2) and Fill(1) and Route())
        """)


class SettingsTests(Case):
    """Options and the menu: the switch, and the two settings it sets shown as set"""

    def test_options(self):
        self.run_lua("""
            local o = mod:Options()
            local function info(key) return { key, type = o[key].type } end
            assert(o.exploreReveal and o.exploreReveal.type == "toggle" and o.exploreReveal.get(info("exploreReveal")) == false)
            assert(not o.unexplored.disabled() and not o.foundOnly.disabled())
            o.exploreReveal.set(info("exploreReveal"), true) Frames()
            assert(mod.db.exploreReveal == true and not Shown("Twin Keep"), "takes effect at once")
            assert(o.unexplored.disabled() and o.unexplored.get() == "hide", "Unexplored areas: greyed, showing Hide")
            assert(o.foundOnly.disabled() and o.foundOnly.get() == true, "Only places you've found: greyed, on")
            assert(mod.db.foundOnly == false and mod.db.unexplored == "show", "their own settings untouched")
            -- (the minimap in the gaps, which nothing can be found for: off while it's on, its own setting kept)
            mod.db.gapMinimap = true
            assert(o.gapMinimap.disabled() and not o.gapMinimap.get() and mod.db.gapMinimap == true)
            o.exploreReveal.set(info("exploreReveal"), false) Frames()
            assert(not o.unexplored.disabled() and o.unexplored.get() == "show" and o.foundOnly.get() == false and Shown("Twin Keep"))
            o.foundOnly.set(info("foundOnly"), true)
            assert(mod.db.foundOnly == true and o.foundOnly.get() == true, "Only places you've found still its own setting")
        """)

    def test_the_menus_rows(self):
        self.run_lua("""
            local rows = Rows()
            -- (no Darken row here: the small world has none of the zones' land masks it needs, as retail's data)
            local set = { "foundOnly", "unexplored.hide", "unexploredOwn" }
            assert(not rows["unexplored.dim"])
            assert(rows.exploreReveal and rows.exploreReveal.note and not rows.exploreReveal.locked)
            assert(rows.exploreReveal[2]() == false)
            for _, id in ipairs(set) do assert(rows[id] and not rows[id].locked and not rows[id].note, id) end
            rows.exploreReveal[3](true) Frames()
            assert(mod.db.exploreReveal == true)
            rows = Rows()
            assert(rows.exploreReveal[2]() == true)
            for _, id in ipairs(set) do assert(rows[id].locked and rows[id].note, id .. ": shown as set, not to be clicked") end
            assert(rows.foundOnly[2]() == true and rows["unexplored.hide"][2]() == true)
            rows.exploreReveal[3](false) Frames()
            rows = Rows()
            for _, id in ipairs(set) do assert(not rows[id].locked, id) end
            assert(rows.foundOnly[2]() == false and rows["unexplored.hide"][2]() == false)
        """)


class MinimapTests(Case):
    """the close-up minimap: with Explore to reveal, only through explored pieces, at every zoom and copy"""

    def setUp(self):
        Case.setUp(self)
        # (the minimap from the whole world in, so every zoom has it: its smaller copies further out, the
        # game's own tiles close up)
        self.run_lua("mod.db.minimap, mod.db.minimapFrom = true, 1 mod:Refresh() Frames()")

    def test_off_the_usual_minimap_and_nothing_of_this(self):
        self.run_lua("""
            local asked = 0
            local tiles = S.ExploredTiles
            S.ExploredTiles = function(...) asked = asked + 1 return tiles(...) end
            local kinds = {}
            for _, view in ipairs(VIEWS) do
                Look(view[1], view[2], view[3], 40) Wait()
                local leaks, shown = Leaks()
                assert(shown > 0 and leaks == shown, "off: the minimap's own pictures, whole")
                for _, r in ipairs(Imagery()) do kinds[type(r.__file)] = true end
            end
            assert(kinds.number and kinds.string, "the game's tiles and the smaller copies both looked at")
            assert(asked == 0, "off: the explored pieces asked for")
        """)

    def test_a_zone_never_visited_has_none_at_any_zoom(self):
        # (the report: zoomed in on a zone never visited, the minimap showed past some zoom)
        self.run_lua("""
            Turn(true)
            for _, view in ipairs(VIEWS) do
                for _, steps in ipairs({ 2, 12, 25, 40, 80 }) do
                    Look(view[1], view[2], view[3], steps) Wait()
                    local _, shown = Leaks()
                    assert(shown == 0, shown .. " pictures of the minimap with nothing explored, at " .. view[1] .. ", " .. view[2] .. " x" .. steps)
                end
            end
        """)

    def test_only_through_explored_pieces_at_every_zoom(self):
        self.run_lua("""
            Turn(true)
            Explore(10, "200:200:100:100")           -- West's first piece
            Explore(20, "300:300:300:200")           -- East's (four tiles)
            local kinds, most = {}, 0
            for _, view in ipairs(VIEWS) do
                for _, steps in ipairs({ 2, 12, 25, 40, 80 }) do
                    Look(view[1], view[2], view[3], steps) Wait()
                    local leaks, shown = Leaks()
                    assert(leaks == 0, leaks .. " of " .. shown .. " pictures not cut to an explored piece, at " .. view[1] .. ", " .. view[2] .. " x" .. steps)
                    most = math.max(most, shown)
                    for _, r in ipairs(Imagery()) do
                        kinds[type(r.__file)] = true
                        -- (each: the part of its picture over that tile, through the land, the piece and the zone's frame)
                        local c = r.__coords
                        assert(c[1] >= -1e-9 and c[2] <= 1 + 1e-9 and c[1] < c[2] and c[3] >= -1e-9 and c[4] <= 1 + 1e-9 and c[3] < c[4])
                        local land, frame = 0, 0
                        for _, mask in ipairs(r.__masks) do
                            local file = tostring(rawget(mask, "__file"))
                            if file:find("MapMiniLand", 1, true) then land = land + 1 end
                            if file:find("MapFeatherThin", 1, true) then
                                -- (its zone's own frame, laid over the zone's map)
                                local z = MAPS[CutTo(r).zone].rect
                                local m0, n0, m1, n1 = Rect(mask)
                                assert(math.abs(m0 - z[1]) < 1e-9 and math.abs(m1 - z[2]) < 1e-9 and math.abs(n0 - z[3]) < 1e-9 and math.abs(n1 - z[4]) < 1e-9)
                                frame = frame + 1
                            end
                        end
                        assert(#r.__masks == 3 and land == 1 and frame == 1, "the continent's land, the piece, the zone's frame: " .. #r.__masks .. " masks")
                    end
                end
            end
            assert(most > 0 and kinds.number and kinds.string, "the game's tiles and the smaller copies, both cut")
            -- where: over the explored pieces, not West's other piece, land under no piece, the sea
            Look(0.3, 0.5, 0.5, 40) Wait()
            assert(Over(0.18, 0.38) and Over(0.19, 0.36), "none over West's explored piece")
            assert(not Over(0.38, 0.56), "over West's unexplored piece")
            assert(not Over(0.45, 0.75) and not Over(0.3, 0.25), "over land under no piece")
            Look(0.68, 0.51, 0.4, 40) Wait()
            for _, at in ipairs({ { 0.66, 0.44 }, { 0.73, 0.5 }, { 0.66, 0.63 }, { 0.73, 0.63 } }) do
                assert(Over(at[1], at[2]), "none over East's piece at " .. at[1] .. ", " .. at[2] .. " (each of its four tiles)")
            end
            assert(not Over(0.8, 0.3) and not Over(0.55, 0.75) and not Over(0.6, 0.5), "past East's piece")
        """)

    def test_the_same_pictures_at_the_same_strengths(self):
        # (what's drawn is the usual minimap's own pictures, as strong: only cut. All of it explored here)
        self.run_lua("""
            for _, key in ipairs({ "10:200:200:100:100", "10:200:200:600:300", "20:300:300:300:200" }) do explored[key] = true end
            S.RefreshExplored() Frames()
            for _, view in ipairs({ { 0.19, 0.38, 0.05 }, { 0.66, 0.44, 0.12 }, { 0.4, 0.5, 0.5 }, { 0.5, 0.5, 0.9 } }) do
                for _, steps in ipairs({ 12, 25, 60 }) do
                    Turn(false)
                    Look(view[1], view[2], view[3], steps) Wait()
                    local usual = {}
                    for _, r in ipairs(Imagery()) do usual[r.__file] = r.__alpha end
                    Turn(true)
                    Look(view[1], view[2], view[3], steps) Wait()
                    local n = 0
                    for _, r in ipairs(Imagery()) do
                        n = n + 1
                        assert(usual[r.__file], "a picture the usual minimap doesn't draw: " .. tostring(r.__file))
                        assert(math.abs(usual[r.__file] - r.__alpha) < 1e-9, "at another strength")
                    end
                    assert(n > 0)
                end
            end
        """)

    def test_a_picture_comes_in_over_a_moment(self):
        self.run_lua("""
            Turn(true)
            Explore(20, "300:300:300:200")
            Look(0.66, 0.44, 0.12, 40)
            local _, shown = Leaks()
            assert(shown == 0, "up the moment it was made: it popped in")
            Wait(0.15)
            local part = Imagery()
            assert(#part > 0, "nothing of it half way in")
            local half = part[1].__alpha
            Wait(0.3)
            local full = Imagery()
            assert(#full == #part)
            assert(half > 0 and half < full[1].__alpha, "half way in at " .. half .. ", in at " .. full[1].__alpha)
            -- (in: the same strength as the usual minimap's, test_the_same_pictures_at_the_same_strengths)
            -- the view moved on: the pictures already up stay up, a new one comes in on its own
            local before = {}
            for _, r in ipairs(full) do before[r] = r.__alpha end
            Look(0.70, 0.50, 0.12, 40)
            local kept, new = 0, 0
            for _, r in ipairs(Imagery()) do
                if before[r] then kept = kept + 1 assert(r.__alpha == before[r], "one already up dipped") end
            end
            assert(kept > 0, "none of those up stayed up through a pan")
            Wait(0.5)
            assert(#Imagery() > kept, "none came in over the ground panned to")
        """)

    def test_explored_with_the_map_still(self):
        self.run_lua("""
            Turn(true)
            Look(0.66, 0.44, 0.12, 40) Wait()
            assert(select(2, Leaks()) == 0)
            Explore(20, "300:300:300:200") Wait()    -- (MAP_EXPLORATION_UPDATED, the view not moved)
            local leaks, shown = Leaks()
            assert(shown > 0 and leaks == 0 and Over(0.66, 0.44), "explored: its minimap without a pan")
        """)

    def test_not_before_the_art_has_it(self):
        # (explored with the map closed: the art is brought up to date as the map next opens, WorldMap.lua's
        # exploredDirty. Until then the piece isn't drawn, and the minimap isn't drawn through it either)
        self.run_lua("""
            Turn(true)
            explored["20:300:300:300:200"] = true    -- (the game has it; the art hasn't been told yet)
            S.RefreshFound() Frames()                -- (what's found looked at again meanwhile: a dungeon entered)
            Look(0.66, 0.44, 0.12, 40) Wait()
            assert(#Imagery() == 0, "the minimap through a piece the art doesn't show yet")
            S.RefreshExplored() Frames() Wait()
            assert(#Imagery() > 0 and Leaks() == 0)
        """)

    def test_no_cover_made_for_tiles_that_arent_drawn(self):
        # (Stitch.lua's cover over the usual tiles, the zone's blank art again over its unexplored pieces:
        # not made, nor drawn, while the tiles themselves aren't)
        self.run_lua("""
            local function blank()                   -- (the zones' base art on screen: files 1001.., 2001..)
                local n = 0
                for _, r in ipairs(FRAMES) do
                    local file = rawget(r, "__file")
                    if r.__kind == "Texture" and type(file) == "number" and file > 1000 and file < 3100 and r.__points[1] and rawget(r, "__shown") ~= false then n = n + 1 end
                end
                return n
            end
            Turn(true)
            Explore(10, "200:200:100:100")
            for _ = 1, 3 do                          -- (the zones' own art in view all loaded and shown first)
                mod.db.minimap = not mod.db.minimap
                Look(0.3, 0.5, 0.5, 40) Wait()
            end
            assert(mod.db.minimap == false)
            local without = blank()
            mod.db.minimap = true
            Look(0.3, 0.5, 0.5, 40) Wait()
            assert(select(2, Leaks()) > 0, "the minimap through the explored piece")
            assert(blank() == without, (blank() - without) .. " textures of the cover made, the tiles it covers not drawn")
        """)

    def test_off_again_the_usual_minimap_and_the_clips_put_away(self):
        self.run_lua("""
            Turn(true)
            Explore(20, "300:300:300:200")
            Look(0.66, 0.44, 0.12, 40) Wait()
            local _, cut = Leaks()
            assert(cut > 0)
            Turn(false)
            Look(0.66, 0.44, 0.12, 40) Wait()
            local leaks, shown = Leaks()
            assert(shown > 0 and leaks == shown, "off again: the usual tiles, and no clip left up")
            -- and on again: the same clips, and the masks, used again (none made anew)
            local made = #FRAMES
            Turn(true)
            Look(0.66, 0.44, 0.12, 40) Wait()
            local leaks2, cut2 = Leaks()
            assert(leaks2 == 0 and cut2 == cut and #FRAMES == made, (#FRAMES - made) .. " regions made anew")
        """)

    def test_masks_let_go_with_their_clips(self):
        # (a mask no clip uses is unanchored: whatever hangs from the map is laid out again on every pan)
        self.run_lua("""
            Turn(true)
            Explore(10, "200:200:100:100")
            Explore(20, "300:300:300:200")
            local function masksUp()
                local n = 0
                for _, r in ipairs(FRAMES) do
                    if r.__kind == "MaskTexture" and TILES[rawget(r, "__file")] and r.__points[1] then n = n + 1 end
                end
                return n
            end
            Look(0.68, 0.51, 0.4, 40) Wait()
            assert(masksUp() == 4, masksUp() .. " masks for East's four tiles")
            Look(0.19, 0.38, 0.05, 40) Wait()
            assert(masksUp() == 1, masksUp() .. " masks with West's one tile in view")
            Look(0.05, 0.9, 0.05, 40) Wait()
            assert(masksUp() == 0 and select(2, Leaks()) == 0, "masks left anchored with nothing explored in view")
        """)


ASK = "OPENMAP_EXPLORE_REVEAL"
# (a login: the loading screen gone, then the few seconds the question waits)
LOGIN = 'FireEvent("LOADING_SCREEN_DISABLED") Frames(3)'


class AskTests(Case):
    """the one-time setup question (Welcome.lua): an account already set up, its first login after the update"""
    saved = '{ worldmap = { enabled = true, presetAsked = true, unexplored = "hide", foundOnly = true, icons = true } }'

    def setUp(self):
        self.lua = world(saved=self.saved)
        self.lua.execute('ASK = "%s"' % ASK)

    def asked(self):
        return self.lua.eval("POPUPS[ASK] ~= nil")

    def test_an_account_already_set_up_is_asked_once_it_logs_in(self):
        # (Unexplored areas: Hide and Only places you've found both on before the update: asked all the same)
        self.assertFalse(self.asked(), "asked before the loading screen had gone")
        # (the loading screen gone: not at once, but after the login's own popups and ClassicUI Forever's
        # question, which Window.lua asks 5 seconds in)
        self.run_lua('FireEvent("LOADING_SCREEN_DISABLED")')
        self.assertFalse(self.asked(), "asked the moment the loading screen went")
        self.assertGreater(self.lua.eval("WAIT"), 5)
        self.run_lua("Frames(3)")
        self.assertTrue(self.asked())
        self.run_lua("""
            assert(mod.db.exploreAsked == nil and mod.db.exploreReveal == false, "nothing set by asking")
            local info = StaticPopupDialogs[ASK]
            assert(info.button1 == "Reveal as I explore" and info.button2 == "Show everything")
            assert(not info.hideOnEscape and info.timeout == 0, "no answer by Escape or by waiting")
            POPUPS[ASK] = nil
            FireEvent("LOADING_SCREEN_DISABLED") Frames(3)       -- (another loading screen: not a second time)
            assert(POPUPS[ASK] == nil, "asked twice in one login")
        """)

    def test_reveal_as_i_explore(self):
        self.run_lua(LOGIN)
        self.run_lua("""
            mod.db.foundOnly, mod.db.unexplored = false, "show"
            mod:Refresh() Frames()
            assert(Shown("Twin Keep") and Fill(1))
            Press(ASK, 1) Frames()
            assert(mod.db.exploreAsked == true and mod.db.exploreReveal == true, "the answer saved")
            assert(not Shown("Twin Keep") and not Fill(1) and mod.Unexplored() == "hide", "at once, no reload")
            assert(LOG[#LOG]:find("/openmap > Look > Explore to reveal", 1, true), "where to change it, said in chat too")
        """)

    def test_show_everything(self):
        self.run_lua(LOGIN)
        self.run_lua("""
            Press(ASK, 2) Frames()
            assert(mod.db.exploreAsked == true and mod.db.exploreReveal == false)
            -- (the settings the account had are its own still: Hide, and only the places found)
            assert(mod.db.unexplored == "hide" and mod.db.foundOnly == true and mod.Unexplored() == "hide" and not Shown("Twin Keep"))
            assert(Fill(1), "... and nothing of Explore to reveal's")
        """)

    def test_gone_without_a_button_it_asks_again_at_the_next_login(self):
        self.run_lua(LOGIN)
        self.run_lua("""
            PushOut(ASK) Frames(5)                   -- (another popup took its place)
            assert(mod.db.exploreAsked == nil and mod.db.exploreReveal == false, "taken as an answer")
            assert(POPUPS[ASK] == nil, "not again in the same login")
            unanswered = OpenMapDB.worldmap.exploreAsked == nil
        """)
        self.assertTrue(self.lua.eval("unanswered"), "saved as answered")
        again = world(saved=self.saved)              # (the next login, the settings as they were saved)
        again.execute('ASK = "%s" ' % ASK + LOGIN)
        self.assertTrue(again.eval("POPUPS[ASK] ~= nil"), "not asked again at the next login")

    def test_answered_it_isnt_asked_again(self):
        for button in (1, 2):
            lua = world(saved=self.saved)
            lua.execute('ASK = "%s" ' % ASK + LOGIN)
            lua.execute("Press(ASK, %d) Frames() saved = OpenMapDB.worldmap" % button)
            self.assertTrue(lua.eval("saved.exploreAsked"))
            reveal = "true" if button == 1 else "false"
            again = world(saved='{ worldmap = { enabled = true, presetAsked = true, exploreAsked = true, exploreReveal = %s } }' % reveal)
            again.execute('ASK = "%s" ' % ASK + LOGIN)
            self.assertFalse(again.eval("POPUPS[ASK] ~= nil"), "asked again after button %d" % button)
            self.assertEqual(again.eval("mod.ExploreReveal()"), button == 1)

    def test_not_in_combat(self):
        self.run_lua("""
            IN_COMBAT = true
            FireEvent("LOADING_SCREEN_DISABLED") Frames(5)
            assert(POPUPS[ASK] == nil, "asked in combat")
            IN_COMBAT = false
            Frames(5)
            assert(POPUPS[ASK] == nil, "not by waiting: as combat ends")
            FireEvent("PLAYER_REGEN_ENABLED") Frames(3)
            assert(POPUPS[ASK] ~= nil, "not asked as combat ended")
            -- (and /openmap setup, typed in combat, says so and shows nothing)
            POPUPS[ASK] = nil
            IN_COMBAT = true
            SlashCmdList.OPENMAP("setup")
            assert(POPUPS[ASK] == nil and LOG[#LOG]:find("Not in combat", 1, true))
        """)

    def test_never_over_openmaps_other_questions(self):
        self.run_lua("""
            -- ClassicUI Forever's question up (Window.lua's): this one waits for its answer
            StaticPopupDialogs.OPENMAP_CLASSICUI_MAP = { text = "%s" }
            StaticPopup_Show("OPENMAP_CLASSICUI_MAP", "")
            FireEvent("LOADING_SCREEN_DISABLED") Frames(6)
            assert(POPUPS[ASK] == nil, "over ClassicUI Forever's question")
            POPUPS.OPENMAP_CLASSICUI_MAP = nil
            Frames(3)
            assert(POPUPS[ASK] ~= nil, "not asked once that was answered")
        """)

    def test_the_gamepad_ui_and_openmap_off(self):
        self.run_lua("""
            -- the Gamepad UI on, the map left to Blizzard: not asked about a map that isn't up
            mod.padWaits = true
            FireEvent("LOADING_SCREEN_DISABLED") Frames(6)
            assert(POPUPS[ASK] == nil)
            mod.PadViewOn = function() return true end       -- (the controller view: OpenMap's map again)
            Frames(3)
            assert(POPUPS[ASK] ~= nil)
        """)
        off = world(saved='{ worldmap = { enabled = false, presetAsked = true } }')
        off.execute('ASK = "%s" ' % ASK + LOGIN + " Frames(5)")
        self.assertFalse(off.eval("POPUPS[ASK] ~= nil"), "asked with OpenMap turned off")

    def test_refused_by_the_game_it_tries_again(self):
        self.run_lua("""
            refusePopups = true                      -- (a cinematic, no room for another popup)
            FireEvent("LOADING_SCREEN_DISABLED") Frames(5)
            assert(POPUPS[ASK] == nil)
            refusePopups = false
            Frames(3)
            assert(POPUPS[ASK] ~= nil)
        """)

    def test_the_text_and_where_to_change_it(self):
        self.run_lua(LOGIN)
        text = self.lua.eval("POPUPS[ASK].text")
        self.assertEqual(text, "\n\n".join([
            "How should OpenMap show the world? You're asked once, for all your characters.",
            "|cffffd100Reveal as I explore|r: unexplored land stays hidden, and dungeons, boats, flight masters and townsfolk show once"
            " the character has found them, as on the game's own map.",
            "|cffffd100Show everything|r: the whole map and every place from the start, as OpenMap has always shown it.",
            "To change it later: /openmap > Look > Explore to reveal\n"
            "Or: Options > AddOns > OpenMap > Open OpenMap's settings > Look > Explore to reveal",
        ]))

    def test_the_path_is_the_interfaces_own_words(self):
        # (another language: each step is the text the interface itself shows there, never a second translation)
        self.run_lua("""
            local L = ns.L
            L["Look"], L["Explore to reveal"], L["Open OpenMap's settings"] = "Aussehen", "Erkunden deckt auf", "OpenMaps Einstellungen"
            L["Reveal as I explore"], L["To change it later: %s"], L["Or: %s"] = "Beim Erkunden", "Später ändern: %s", "Oder: %s"
            GAMEMENU_OPTIONS, SETTINGS_TAB_ADDONS = "Optionen", "Add-ons"      -- (the game's own, in that client)
            local menu, options = mod.ExplorePaths()
            assert(menu == "/openmap > Aussehen > Erkunden deckt auf", menu)
            assert(options == "Optionen > Add-ons > OpenMap > OpenMaps Einstellungen > Aussehen > Erkunden deckt auf", options)
            -- ... which are the menu's own tab and row, and the options' own heading and switch
            local rows = Rows()
            assert(rows.exploreReveal[1] == "Erkunden deckt auf")
            local o = mod:Options()
            assert(o.exploreReveal.name == "Erkunden deckt auf" and o.lookHeader.name == "Aussehen")
            StaticPopupDialogs[ASK] = nil
            mod:AskExplore()
            local text = POPUPS[ASK].text
            assert(text:find("Später ändern: /openmap > Aussehen > Erkunden deckt auf\\nOder: Optionen > Add-ons > OpenMap > OpenMaps Einstellungen > Aussehen > Erkunden deckt auf", 1, true), text)
            assert(text:find("|cffffd100Beim Erkunden|r", 1, true) and StaticPopupDialogs[ASK].button1 == "Beim Erkunden", "the button's own name in the text")
        """)

    def test_openmap_setup_asks_again(self):
        self.run_lua(LOGIN)
        self.run_lua("""
            Press(ASK, 2) Frames()
            SlashCmdList.OPENMAP("setup")
            assert(POPUPS[ASK] ~= nil, "/openmap setup")
            Press(ASK, 1) Frames()
            assert(mod.db.exploreReveal == true and mod.db.exploreAsked == true)
        """)

    def test_answered_by_openmap_setup_while_the_question_waited(self):
        self.run_lua("""
            StaticPopupDialogs.OPENMAP_CLASSICUI_MAP = { text = "%s" }
            StaticPopup_Show("OPENMAP_CLASSICUI_MAP", "")    -- (ClassicUI Forever's question up: this one waits)
            FireEvent("LOADING_SCREEN_DISABLED") Frames(4)
            SlashCmdList.OPENMAP("setup")
            Press(ASK, 2)
            POPUPS.OPENMAP_CLASSICUI_MAP = nil
            Frames(4)
            assert(POPUPS[ASK] == nil, "asked again, though answered meanwhile")
        """)


class NewInstallTests(Case):
    """a new install: the question at its first login, and the choice of map (Classic or OpenMap) as the map
    first opens, one at a time"""

    def setUp(self):
        self.lua = world(saved="nil")
        self.lua.execute('ASK = "%s"' % ASK)
        self.lua.execute("""
            local function upvalue(fn, wanted)
                for i = 1, 60 do
                    local name, value = debug.getupvalue(fn, i)
                    if name == wanted then return value end
                end
            end
            -- the choice's window (Welcome.lua's), and one of its two buttons pressed (1: Classic, 2: OpenMap)
            function Welcome() return upvalue(mod.ShowWelcome, "frame") end
            function Pick(n)
                local seen = 0
                for _, child in ipairs({ Welcome():GetChildren() }) do
                    if child:GetObjectType() == "Button" and child:GetScript("OnClick") and child.__text ~= nil then
                        seen = seen + 1
                        if seen == n then return child:GetScript("OnClick")(child) end
                    end
                end
                error("no button " .. n)
            end
        """)

    def test_asked_at_its_first_login_too(self):
        self.run_lua("assert(mod.fresh and mod.db.presetAsked == false and mod.db.exploreAsked == nil)")
        self.run_lua(LOGIN)
        self.assertTrue(self.lua.eval("POPUPS[ASK] ~= nil"))

    def test_the_choice_of_map_waits_for_the_answer(self):
        self.run_lua(LOGIN)
        self.run_lua("""
            mod.WelcomeIfDue()                       -- (the map opened with the question still up)
            assert(not (Welcome() and Welcome():IsShown()), "the choice of map over the question")
            Press(ASK, 1) Frames()
            assert(Welcome() and Welcome():IsShown(), "the choice of map once it was answered")
            -- neither of its presets undoes the answer
            Pick(1)
            assert(mod.db.presetAsked == true and mod.db.unexplored == "hide" and mod.db.exploreReveal == true)
        """)

    def test_the_question_waits_for_the_choice_of_map(self):
        self.run_lua("""
            mod:ShowWelcome()                        -- (the map opened first)
            assert(Welcome():IsShown())
            FireEvent("LOADING_SCREEN_DISABLED") Frames(6)
            assert(POPUPS[ASK] == nil, "the question over the choice of map")
            Pick(2)
            assert(not Welcome():IsShown() and mod.db.exploreReveal == false)
            Frames(3)
            assert(POPUPS[ASK] ~= nil, "asked once the choice was made")
        """)


class ClassicQuestionTests(unittest.TestCase):
    """ClassicUI Forever's question (Window.lua's AskClassicMap, its source alone) never comes up over the
    one-time setup question: it waits for that one's answer, and isn't counted as asked meanwhile"""

    def setUp(self):
        src = (ADDON / "Map" / "Window.lua").read_text(encoding="utf-8")
        m = re.search(r"\nlocal function AskClassicMap\(\)\n.*?\nend\n", src, re.S)
        self.assertIsNotNone(m, "AskClassicMap in Window.lua")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            asking, combat, shown, later = true, false, {}, {}
            afterCombat = false
            mod = { db = {}, ExploreAsking = function() return asking end }
            ns = { Print = function() end }
            L = setmetatable({}, { __index = function(_, k) return k end })
            StaticPopupDialogs = {}
            function InCombatLockdown() return combat end
            function StaticPopup_Show(which) shown[#shown + 1] = which end
            C_Timer = { After = function(_, fn) later[#later + 1] = fn end }
        """)
        self.lua.execute("local AskClassicMap\n" + m.group(0).replace("local function AskClassicMap()", "function AskClassicMap()", 1)
                         + "\nAsk = AskClassicMap")

    def test_waits_for_the_setup_questions_answer(self):
        self.lua.execute("""
            Ask()
            assert(#shown == 0 and not mod.db.classicMapAsked, "over the setup question, or counted as asked")
            assert(#later == 1, "not tried again")
            asking = false
            later[1]()
            assert(#shown == 1 and shown[1] == "OPENMAP_CLASSICUI_MAP" and mod.db.classicMapAsked == true)
        """)


class TranslationTests(unittest.TestCase):
    """the setup question's texts in every language's JSON and built file: real UTF-8, read back as written
    (text written through the wrong encoding reads as "Ã¤" for "ä": none of that), a %s where the English
    has one, and nothing that names a step of the click path (those are put in by the code, each as the
    interface names it)"""
    TEXTS = [
        "How should OpenMap show the world? You're asked once, for all your characters.",
        "Reveal as I explore",
        "Show everything",
        "%s: unexplored land stays hidden, and dungeons, boats, flight masters and townsfolk show once the character has found them, as on the game's own map.",
        "%s: the whole map and every place from the start, as OpenMap has always shown it.",
        "To change it later: %s",
        "Or: %s",
    ]
    LOCALES = ["deDE", "esES", "esMX", "frFR", "itIT", "koKR", "ptBR", "ruRU", "zhCN", "zhTW"]

    @staticmethod
    def twice_encoded(text):
        """whether the text is UTF-8 that was read as Windows-1252 or Latin-1 and written as UTF-8 again"""
        for wrong in ("cp1252", "latin-1"):
            try:
                if text.encode(wrong).decode("utf-8") != text:
                    return True
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return False

    def test_every_language_has_them_as_written(self):
        code = (ADDON / "Map" / "Welcome.lua").read_text(encoding="utf-8")
        for en in self.TEXTS:
            self.assertIn('L["%s"]' % en, code, "the text the code asks for")
        for loc in self.LOCALES:
            tr = json.loads((ROOT / "tools" / "locale" / (loc + ".json")).read_bytes().decode("utf-8"))
            built = (ADDON / "Locales" / (loc + ".lua")).read_bytes().decode("utf-8")
            for en in self.TEXTS:
                t = tr.get(en)
                self.assertTrue(t, "%s: %r" % (loc, en))
                self.assertFalse(self.twice_encoded(t), "%s: %r is encoded twice" % (loc, t))
                self.assertEqual(t.count("%s"), en.count("%s"), (loc, en))
                self.assertNotIn(" > ", t, (loc, en))
                self.assertNotIn("/openmap", t, (loc, en))
                self.assertIn('L["%s"] = "%s"' % (en, t), built, "%s: built as written" % loc)

    def test_german_has_its_umlauts(self):
        tr = json.loads((ROOT / "tools" / "locale" / "deDE.json").read_bytes().decode("utf-8"))
        self.assertEqual(tr["To change it later: %s"], "Sp\u00e4ter \u00e4ndern: %s")
        self.assertIn("f\u00fcr alle Eure Charaktere", tr[self.TEXTS[0]])
        raw = (ADDON / "Locales" / "deDE.lua").read_bytes()
        self.assertIn("Sp\u00e4ter \u00e4ndern".encode("utf-8"), raw)          # (c3 a4: one character each)
        self.assertNotIn("Sp\u00c3\u00a4ter".encode("utf-8"), raw)             # ("SpÃ¤ter": encoded twice)


class OverTests(unittest.TestCase):
    """Stitch.lua's Shade.Over alone: the pieces whose rectangle reaches into a box on the world, for
    random zones, pieces and boxes, against each rectangle worked out here; and what it's for (Shade.Found):
    a painted gap is found once one of them is explored, or with none there"""

    def setUp(self):
        src = (ADDON / "Map" / "Stitch.lua").read_text(encoding="utf-8")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            W, H, NONE = 1002, 668, {}
            pieces, placed, Shade = {}, {}, {}
            function Place(zoneID) return placed[zoneID] end
            function strsplit(sep, s)
                local out = {}
                for part in (s .. sep):gmatch("(.-)" .. sep) do out[#out + 1] = part end
                return unpack(out)
            end
        """)
        for name in ("Shade.Over", "Shade.Found"):
            m = re.search(r"\nfunction %s\(.*?\nend\n" % re.escape(name), src, re.S)
            self.assertIsNotNone(m, name + " in Stitch.lua")
            self.lua.execute(m.group(0))

    def test_random_pieces_against_each_rectangle(self):
        rng = random.Random(11)
        for _ in range(150):
            self.lua.execute("pieces, placed = {}, {}")
            rects = []                          # (zone, key, the piece's rectangle on the world, normalized)
            for zone in range(1, rng.randint(2, 5)):
                left, top = rng.uniform(0, 700), rng.uniform(0, 400)
                sx, sy = rng.uniform(0.1, 0.4), rng.uniform(0.1, 0.4)
                placed = rng.random() < 0.9     # (a zone that can't be placed: its pieces are over nothing)
                if placed:
                    self.lua.execute("placed[%d] = { left = %r, top = %r, sx = %r, sy = %r }" % (zone, left, top, sx, sy))
                self.lua.execute("pieces[%d] = {}" % zone)
                for _ in range(rng.randint(0, 6)):
                    w, h, x, y = rng.randint(20, 300), rng.randint(20, 300), rng.randint(0, 700), rng.randint(0, 400)
                    key = "%d:%d:%d:%d" % (w, h, x, y)
                    self.lua.execute('pieces[%d]["%s"] = { zone = %d, key = "%s" }' % (zone, key, zone, key))
                    if placed:
                        rects.append((zone, key, (left + x * sx) / 1002, (top + y * sy) / 668,
                                      (left + (x + w) * sx) / 1002, (top + (y + h) * sy) / 668))
            boxes = []
            for _ in range(rng.randint(1, 4)):
                l, t = rng.uniform(0, 0.9), rng.uniform(0, 0.9)
                boxes.append((l, t, l + rng.uniform(0.01, 0.3), t + rng.uniform(0.01, 0.3)))
            self.lua.execute("boxes = { %s }" % ", ".join("{ %r, %r, %r, %r }" % b for b in boxes))
            out = self.lua.eval("Shade.Over(boxes)")
            self.assertEqual(len(out), len(boxes))
            for i, (l, t, r, b) in enumerate(boxes, 1):
                got = sorted((p.zone, p.key) for p in out[i].values())
                want = sorted((z, k) for z, k, x0, y0, x1, y1 in rects if x1 > l and x0 < r and y1 > t and y0 < b)
                self.assertEqual(got, want)

    def test_found_once_a_piece_over_it_is_explored_or_with_none(self):
        self.lua.execute("""
            placed[1] = { left = 0, top = 0, sx = 1, sy = 1 }
            pieces[1] = { ["100:100:0:0"] = { unexplored = true }, ["100:100:500:300"] = { unexplored = true } }
            over = Shade.Over({ { 0.05, 0.05, 0.2, 0.2 }, { 0.3, 0.1, 0.4, 0.2 } })
        """)
        found = self.lua.eval("function() return Shade.Found(over[1]), Shade.Found(over[2]) end")
        self.assertEqual(found(), (False, True))          # (a piece over the first, unexplored; none over the second)
        self.lua.execute('pieces[1]["100:100:500:300"].unexplored = false')
        self.assertEqual(found(), (False, True))          # (a piece elsewhere explored: not the one over it)
        self.lua.execute('pieces[1]["100:100:0:0"].unexplored = false')
        self.assertEqual(found(), (True, True))


if __name__ == "__main__":
    unittest.main()
