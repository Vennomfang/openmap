--------------------------------------------------------------------------------
-- The first time the map opens on a new install: how it starts out. "Classic" is closer to
-- Blizzard's map: unexplored areas hidden, none of OpenMap's own icons or zone levels, the
-- favourites folded away. "OpenMap" keeps OpenMap's defaults. Settings saved before this are
-- never asked about, or changed. /openmap welcome asks again.
--
-- And the one question every account is asked, once (below): Explore to reveal, or everything shown.
--------------------------------------------------------------------------------

local _, ns = ...
local mod = ns:GetModule("worldmap")
local L = ns.L

-- (presetAsked isn't in the defaults, where old saves would get it too: nil until the first login
-- with this version, then false on a new install, asked when the map opens, and true on one that
-- had settings)
local CLASSIC = { unexplored = "hide", icons = false, boats = false, zeppelins = false, flight = false, routes = false, zoneLevels = false,
	dungeonLevels = false, trayOpen = false }

local frame

-- (neither choice touches Explore to reveal: that's the one-time setup question's, below)
local function Choose(classic)
	mod.db.presetAsked = true
	if classic then
		for k, v in pairs(CLASSIC) do mod.db[k] = v end
		mod:Refresh()
		if ns.NotifyOptions then ns.NotifyOptions() end
	end
	frame:Hide()
end

local function Build(map)
	frame = CreateFrame("Frame", nil, map)
	frame:SetSize(480, 196)
	frame:SetPoint("CENTER", map.ScrollContainer or map, "CENTER")
	frame:SetFrameStrata("DIALOG")
	frame:EnableMouse(true)         -- (clicks don't reach the map under it)
	if mod.padRoots then mod.padRoots[#mod.padRoots + 1] = frame end   -- (the gamepad's cursor presses its buttons: Gamepad.lua)
	-- (in the map window's own frame, as What's new is; no X: a choice is wanted, and the map's own
	-- close asks again next time)
	local top, _, close = ns.Look:Window(frame, L["Choose your map"])
	close:Hide()
	local text = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	text:SetPoint("TOP", 0, -top - 14)
	text:SetWidth(440)
	text:SetText(L["You can change any of it later in OpenMap's menu (its button on the map, or /openmap)."])
	local function Choice(x, label, desc, classic)
		local b = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
		b:SetSize(180, 28)
		b:SetPoint("TOP", frame, "TOP", x, -top - 54)
		b:SetText(label)
		b:SetScript("OnClick", function() Choose(classic) end)
		local fs = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
		fs:SetPoint("TOP", b, "BOTTOM", 0, -8)
		fs:SetWidth(200)
		fs:SetText(desc)
	end
	Choice(-106, L["Classic"], L["Unexplored areas hidden. No dungeon or flight master icons and no zone levels."], true)
	Choice(106, L["OpenMap"], L["Show the whole map, with dungeon entrances, flight masters, zone levels and favourite buttons."], false)
	frame:Hide()
end

function mod:ShowWelcome()
	local map = WorldMapFrame
	if not map then return end
	if not frame then Build(map) end
	if map:IsShown() then frame:Show() return end
	ToggleWorldMap()
	C_Timer.After(0, function() if map:IsShown() then frame:Show() end end)
end

-- the map shown on a new install not asked yet: the choice (not over the question below while that's up:
-- it comes once that's answered)
function mod.WelcomeIfDue()
	if mod.enabled and mod.db.presetAsked == false and not (frame and frame:IsShown()) and not mod.ExploreAsking() then mod:ShowWelcome() end
end

--------------------------------------------------------------------------------
-- The one-time setup question: Explore to reveal (the map opens up as the character explores:
-- WorldMap.lua's mod.ExploreReveal), or everything shown as OpenMap has shown it. Every account is asked
-- once, a new install and one set up long ago alike, a few seconds into the first login with a version
-- that has the option. The answer is the player's own: `exploreAsked` (saved with the account's settings,
-- not among the defaults) is set only by one of its two buttons, so a question that goes without one (it
-- has no Escape and no timeout; another popup can still push it out) is asked again at the next login.
-- Never over OpenMap's other questions (the choice above, ClassicUI Forever's: Window.lua), in combat
-- (as it ends), before the loading screen has gone, or while the Gamepad UI has OpenMap stand down.
-- The two presets above leave the answer alone: they set the icons and the look, and Explore to reveal,
-- when on, is what says how much of the map shows. /openmap setup asks again.
-- (One table: after, again: seconds; tries: how often the game may refuse the popup before it's left
-- for the next login)
--------------------------------------------------------------------------------

local ASK = "OPENMAP_EXPLORE_REVEAL"
local ask = { owner = {}, after = 8, again = 2, tries = 30 }

function mod.ExploreAsking()
	return StaticPopup_Visible ~= nil and StaticPopup_Visible(ASK) ~= nil
end

-- where to change it later, as the steps to click with " > " between, each as the interface itself names
-- it in the client's language (never translated again inside a sentence): the menu's own tab and row
-- (Panel.lua's), and the way in through the game's Options (its own words for them, and Init.lua's page)
function mod.ExplorePaths()
	local look, row = L["Look"], L["Explore to reveal"]
	return table.concat({ "/openmap", look, row }, " > "),
		table.concat({ GAMEMENU_OPTIONS or "Options", SETTINGS_TAB_ADDONS or ADDONS or "AddOns", "OpenMap",
			L["Open OpenMap's settings"], look, row }, " > ")
end

local function Answer(on)
	mod.db.exploreAsked = true
	mod.db.exploreReveal = on and true or false
	mod:Refresh()                   -- (at once: no reload)
	if ns.NotifyOptions then ns.NotifyOptions() end
	ns:Print(L["To change it later: %s"], (mod.ExplorePaths()))
	-- (a new install's choice of map, held back while this was up)
	if WorldMapFrame and WorldMapFrame:IsShown() then mod.WelcomeIfDue() end
end

local function ShowAsk()
	local gold = "|cffffd100%s|r"
	local yes, no = L["Reveal as I explore"], L["Show everything"]
	local menu, options = mod.ExplorePaths()
	StaticPopupDialogs[ASK] = StaticPopupDialogs[ASK] or {
		text = "%s",
		button1 = yes,
		button2 = no,
		OnAccept = function() Answer(true) end,
		-- (the second button alone: put out by another popup, it's no answer)
		OnCancel = function(_, _, reason) if reason == "clicked" then Answer(false) end end,
		timeout = 0,
		whileDead = 1,
		hideOnEscape = false,
		noCancelOnEscape = 1,
		preferredIndex = 3,
	}
	return StaticPopup_Show(ASK, table.concat({
		L["How should OpenMap show the world? You're asked once, for all your characters."],
		L["%s: unexplored land stays hidden, and dungeons, boats, flight masters and townsfolk show once the character has found them, as on the game's own map."]:format(gold:format(yes)),
		L["%s: the whole map and every place from the start, as OpenMap has always shown it."]:format(gold:format(no)),
		L["To change it later: %s"]:format(menu) .. "\n" .. L["Or: %s"]:format(options),
	}, "\n\n"))
end

-- asked once it can be; until then, again in a moment (in combat: as it ends)
local function TryAsk()
	-- (answered meanwhile, by /openmap setup: not again)
	if mod.db.exploreAsked or not mod.db.enabled or not StaticPopup_Show then return end
	if InCombatLockdown() then
		ns.RegisterEvent(ask.owner, "PLAYER_REGEN_ENABLED", function()
			ns.UnregisterEvent(ask.owner, "PLAYER_REGEN_ENABLED")
			C_Timer.After(1, TryAsk)
		end)
		return
	end
	local waits = (frame and frame:IsShown())                                         -- the choice above
		or (StaticPopup_Visible ~= nil and StaticPopup_Visible("OPENMAP_CLASSICUI_MAP") ~= nil)   -- ClassicUI Forever's
		or (mod.padWaits and not (mod.PadViewOn and mod.PadViewOn()))                   -- the map left to Blizzard
	if not waits then
		if ShowAsk() then return end
		ask.tries = ask.tries - 1   -- (refused: a cinematic, no room for another popup)
		if ask.tries <= 0 then return end
	end
	C_Timer.After(ask.again, TryAsk)
end

-- /openmap setup: the question again, answered before or not
function mod:AskExplore()
	if InCombatLockdown() then ns:Print(L["Not in combat."]) return end
	if not StaticPopup_Show or mod.ExploreAsking() then return end
	ShowAsk()
end

local function AskSoon()
	ns.UnregisterEvent(ask.owner, "LOADING_SCREEN_DISABLED")
	ns.UnregisterEvent(ask.owner, "PLAYER_ENTERING_WORLD")
	C_Timer.After(ask.after, TryAsk)   -- (after the login's own popups, and ClassicUI Forever's question)
end

local boot = CreateFrame("Frame")
boot:RegisterEvent("PLAYER_LOGIN")
boot:SetScript("OnEvent", function(self)
	self:UnregisterEvent("PLAYER_LOGIN")
	-- (the question: once the loading screen has gone)
	if not mod.db.exploreAsked and not ns.RegisterEvent(ask.owner, "LOADING_SCREEN_DISABLED", AskSoon) then
		ns.RegisterEvent(ask.owner, "PLAYER_ENTERING_WORLD", AskSoon)
	end
	if mod.db.presetAsked == nil then mod.db.presetAsked = not mod.fresh end
	if mod.db.presetAsked then return end
	EventUtil.ContinueOnAddOnLoaded("Blizzard_WorldMap", function()
		WorldMapFrame:HookScript("OnShow", mod.WelcomeIfDue)
	end)
end)
