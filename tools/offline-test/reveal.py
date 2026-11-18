"""Explore to reveal (Options', the menu's; off unless chosen) in Lua 5.1: the map shows only what this
character has found. The whole addon is loaded as run.py loads it (its toc's files, less the client's
data), in a stubbed client with a small world of its own: one continent, two zones side by side with
explored-area pieces, a city, dungeons, docks and a boat between them, flight masters, townsfolk and two
painted gaps. The stitched map is built on it (Stitch.lua's S.Build) and the real option switched, so
what's checked is the addon's own code from the setting to the icons: which icons, routes, painted gaps
and search results show for what has been explored, that exploring brings them out, and that with the
option off nothing is hidden and nothing is looked up. (A stub: it can't see the art, nor what the game's
own frames and lookups do; docs/testing.md has the in-game check.) Then Stitch.lua's Shade.Over alone,
against every rectangle of random pieces.
python -P tools/offline-test/reveal.py. Needs lupa."""
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
	[120] = { ["300:300:300:200"] = "1201" },                                 -- East's
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
	-- (the continent's corners in yards: 1000 yards a side, x up the map and y across it, as the game's)
	GetWorldPosFromMapPos = function(id, pos)
		if id == 1415 then return 0, { x = (1 - pos.y) * 1000, y = (1 - pos.x) * 1000 } end
	end,
}
-- world yards (x, y) of a point on the world (normalized)
function Yards(u, v) return (1 - v) * 1000, (1 - u) * 1000 end
C_MapExplorationInfo = {
	GetExploredMapTextures = function(id)
		local out = {}
		for key, files in pairs(PIECES[MAPS[id] and MAPS[id].art or 0] or {}) do
			if explored[id .. ":" .. key] then
				local w, h, x, y = strsplit(":", key)
				out[#out + 1] = { textureWidth = tonumber(w), textureHeight = tonumber(h), offsetX = tonumber(x), offsetY = tonumber(y),
					fileDataIDs = { tonumber(files) }, isShownByMouseOver = false }
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
-- timers a frame at a time (Frames), so what's done in one can be counted
QUEUE = {}
C_Timer.After = function(_, fn) QUEUE[#QUEUE + 1] = fn end
function Frames(n)
	for _ = 1, n or 50 do
		local q = QUEUE
		if #q == 0 then return end
		QUEUE, NOW = {}, NOW + 0.016
		for _, fn in ipairs(q) do fn() end
	end
end

local wx1, wy1 = Yards(0.38, 0.56)      -- West's dock, on its second piece
local wx2, wy2 = Yards(0.68, 0.47)      -- East's, on its piece
local fx1, fy1 = Yards(0.19, 0.41)      -- flight masters: West's camp, a post between, East's camp
local fx2, fy2 = Yards(0.45, 0.50)
local fx3, fy3 = Yards(0.70, 0.45)
local data = {
	MapReveal = PIECES,
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


def world(reveal=False):
    """the addon loaded and the stitched map built on the small world (Explore to reveal as saved: `reveal`)"""
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
