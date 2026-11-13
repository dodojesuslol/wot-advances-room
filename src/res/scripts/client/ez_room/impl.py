# -*- coding: utf-8 -*-
# EZ ROOM for ADV: implementation. Loaded by gui/mods/mod_ez_room.py, either as the packaged
# module or, in dev mode, straight from the project source.
# Since 0.8.0 WG's Flash room (fortClanBattleRoom.swf) is never opened. This view does what WG's
# StrongholdBattleRoom + StrongholdBattleRoomWindow did: it listens to the stronghold unit entity
# (IUnitListener / IStrongholdListener, the same callbacks and event bus events), builds the same
# VOs with WG's own Python builders (vo_converters, StrongholdActionButtonStateVO, rally_dps) and
# runs every action through WG's prb API (unit request contexts, entity methods). The web UI gets
# one JSON string, only when something changed.
import json
import logging
import os
import time
import weakref

import BigWorld
import Event
from frameworks.wulf import ViewFlags, ViewModel, ViewSettings, WindowFlags, WindowLayer
from gui.impl.gen import R
from gui.impl.pub import ViewImpl
from gui.impl.pub.window_impl import WindowImpl
from gui.Scaleform.locale.TOOLTIPS import TOOLTIPS
from gui.prb_control.entities.listener import IGlobalListener
from gui.shared.utils.functions import getArenaGeometryName
from helpers import dependency, getClientLanguage
from helpers.i18n import makeString
from adisp import adisp_process
from skeletons.gui.impl import IGuiLoader

__version__ = '0.8.15'
_logger = logging.getLogger('EZ_ROOM')
_logger.setLevel(logging.INFO)
_LAYOUT_PATH = ('ez_room', 'views', 'EzRoomView')
_UI_DIR = 'res/gui/gameface/mods/ez_room'
_SNAPSHOT_FILE = os.path.join('mods', 'configs', 'ez_room', 'last_room.json')  # dev only, for the preview
_SETTINGS_FILE = os.path.join('mods', 'configs', 'ez_room', 'settings.json')  # UI settings (sorting, position, ...)
ROOM_ALIAS = 'StrongholdBattleRoomWindow'  # FORTIFICATION_ALIASES.STRONGHOLD_BATTLE_ROOM_WINDOW_ALIAS
_READY_TIMEOUT = 6.0  # s for the web UI to report itself, else WG's room is opened instead
_CHAT_LINES = 150
_PANEL_W, _PANEL_H = 1038, 707  # size of the room panel (same as WG's whole room window)

# set by the loader in dev mode: contents of dev.json ({'src': 'X:/.../src', ...})
DEV = None


def _devFlag(name):
    # dev.json is read fresh here, so flags can be switched without a restart
    try:
        with open(os.path.join('mods', 'configs', 'ez_room', 'dev.json')) as f:
            return bool(json.load(f).get(name))
    except Exception:
        return False

_settings = None  # cache of settings.json (read once, then only written)


def loadSettings():
    global _settings
    if _settings is None:
        _settings = {}
        try:
            if os.path.isfile(_SETTINGS_FILE):
                with open(_SETTINGS_FILE, 'r') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _settings = data
        except Exception:
            _logger.exception('reading %s failed', _SETTINGS_FILE)
    return dict(_settings)


def saveSettings(settings):
    global _settings
    _settings = dict(settings)
    try:
        folder = os.path.dirname(_SETTINGS_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
    except Exception:
        _logger.exception('writing %s failed', _SETTINGS_FILE)


_LANGS = ('de', 'en', 'pl', 'cs', 'fr', 'es', 'it', 'tr', 'ru')


def _lang():
    try:
        # client language code for the UI texts (app.js TR table); anything else -> English
        code = (getClientLanguage() or '').lower()[:2]
        code = {'cz': 'cs'}.get(code, code)
        return code if code in _LANGS else 'en'
    except Exception:
        return 'en'


def _u(value):
    if isinstance(value, str):
        return value.decode('utf-8', 'replace')
    return value if value is not None else u''


def _clean(value, depth=0):
    # VOs -> JSON-safe values (utf-8 byte strings to unicode, unknown objects to repr)
    if depth > 12:
        return None
    if isinstance(value, str):
        return value.decode('utf-8', 'replace')
    if isinstance(value, (unicode, bool, int, long, float)) or value is None:
        return value
    if isinstance(value, dict):
        return dict(((_u(k) if isinstance(k, str) else unicode(k)), _clean(v, depth + 1)) for k, v in value.iteritems())
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(v, depth + 1) for v in value]
    return _u(repr(value))


def _devUI():
    if not DEV:
        return u''
    try:
        files = {}
        for name in ('style.css', 'app.js'):
            with open(os.path.join(DEV['src'], _UI_DIR, name), 'rb') as f:
                files[name] = f.read().decode('utf-8')
        return json.dumps({'css': files['style.css'], 'js': files['app.js']})
    except Exception:
        _logger.exception('dev: reading UI files failed')
        return u''


# --- WG prb access ---------------------------------------------------------------------

def _dispatcher():
    from gui.prb_control.dispatcher import g_prbLoader
    return g_prbLoader.getDispatcher()


def roomEntity():
    # WG's stronghold unit entity while the player is in a room (not the web room list, whose
    # StrongholdBrowserEntity keeps WG's own Flash window), else None
    try:
        dispatcher = _dispatcher()
        entity = dispatcher.getEntity() if dispatcher is not None else None
        if entity is None or not hasattr(entity, 'isStrongholdSettingsValid'):
            return None
        from gui.prb_control.settings import FUNCTIONAL_FLAG
        flags = entity.getFunctionalFlags()
        if not (flags & FUNCTIONAL_FLAG.UNIT and flags & FUNCTIONAL_FLAG.STRONGHOLD):
            return None
        return entity if entity.getID() > 0 else None
    except Exception:
        _logger.exception('room entity lookup failed')
        return None


@adisp_process
def _sendRequest(ctx):
    # same as BaseRallyRoomView.sendRequest: dispatcher checks cooldowns and shows WG's messages
    dispatcher = _dispatcher()
    if dispatcher is not None:
        yield dispatcher.sendPrbRequest(ctx)


@adisp_process
def _leave(isExit):
    # WG's X (AbstractRallyWindow._doLeave, isExit True) / back link (isExit False): WG's leave
    # confirmation dialog included
    from gui.prb_control.entities.base.ctx import LeavePrbAction
    dispatcher = _dispatcher()
    if dispatcher is not None:
        yield dispatcher.doLeaveAction(LeavePrbAction(isExit=isExit))


def _clientID():
    from constants import PREBATTLE_TYPE
    from messenger.ext import channel_num_gen
    return channel_num_gen.getClientID4Prebattle(PREBATTLE_TYPE.STRONGHOLD)


def _carouselOpenState(flag):
    # same as StrongholdBattleRoomWindow.__updateWindowOpenState (carousel item shown as open)
    from gui.Scaleform.genConsts.MESSENGER_CHANNEL_CAROUSEL_ITEM_TYPES import MESSENGER_CHANNEL_CAROUSEL_ITEM_TYPES
    from gui.shared import g_eventBus
    from gui.shared.event_bus import EVENT_BUS_SCOPE
    from gui.shared.events import ChannelCarouselEvent
    g_eventBus.handleEvent(ChannelCarouselEvent(None, ChannelCarouselEvent.ON_WINDOW_CHANGE_OPEN_STATE, _clientID(),
                                                MESSENGER_CHANNEL_CAROUSEL_ITEM_TYPES.CHANNEL_CAROUSEL_ITEM_TYPE_PREBATTLE, flag),
                           scope=EVENT_BUS_SCOPE.LOBBY)


def destroyWgRoomWindow():
    # WG's Flash room window (web room list phase) when the player has just joined a room
    try:
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from skeletons.gui.app_loader import IAppLoader
        app = dependency.instance(IAppLoader).getApp()
        if app is None or app.containerManager is None:
            return
        view = app.containerManager.getView(WindowLayer.WINDOW, criteria={POP_UP_CRITERIA.VIEW_ALIAS: ROOM_ALIAS})
        if view is not None:
            _logger.info("closing WG's Flash room window")
            view.destroy()
    except Exception:
        _logger.exception("closing WG's room window failed")


# --- texts and small VOs (unchanged from 0.7) ---------------------------------------------

def _backLink(entity):
    # WG's back link (FortClanBattleRoom.backBtn, visible when canGoBack = entity.canKeepMode())
    try:
        if not entity.canKeepMode():
            return {'label': u'', 'tip': u''}
        return {'label': _u(makeString(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_LEAVEBTN_HEADER)),
                'tip': _u(makeString(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_LEAVEBTN_BODY))}
    except Exception:
        _logger.exception('back link text failed')
        return {'label': u'', 'tip': u''}


def _speaking(slots, candidates, events):
    # dbIDs speaking in WG's voice chat: WG's own check (VOIPChatController.isPlayerSpeaking, False
    # while voice chat is off) overridden by the live onPlayerSpeaking events seen since opening
    ids = set()
    for slot in slots:
        player = slot.get('player') if isinstance(slot, dict) else None
        if isinstance(player, dict) and player.get('dbID'):
            ids.add(player['dbID'])
    for cand in candidates:
        if isinstance(cand, dict) and cand.get('dbID'):
            ids.add(cand['dbID'])
    isSpeaking = None
    try:
        from messenger.m_constants import PROTO_TYPE
        from messenger.proto import proto_getter
        isSpeaking = proto_getter(PROTO_TYPE.BW_CHAT2)(None).voipController.isPlayerSpeaking
    except Exception:
        _logger.exception('voip controller lookup failed')
    result = []
    for dbID in ids:
        try:
            on = events[dbID] if dbID in events else bool(isSpeaking and isSpeaking(dbID))
        except Exception:
            on = False
        if on:
            result.append(dbID)
    return result


def _roleRights(entity, slots):
    # per player: may I give / take each role? Same checks as WG's context menu
    # (UnitUserCMHandler._canGiveEquipmentCommander / _canTakeEquipmentCommander)
    rights = {}
    try:
        from gui.prb_control.items.stronghold_items import BOOST_TYPE, SUPPORT_TYPE
        if not entity.getPermissions().canChangeExtraEquipmentRole():
            return rights
        for slot in slots:
            player = slot.get('player') if isinstance(slot, dict) else None
            dbID = player.get('dbID') if isinstance(player, dict) else None
            if not dbID:
                continue
            pInfo = entity.getPlayerInfo(dbID=dbID)
            if not pInfo.isInSlot:
                continue
            perms = entity.getPermissions(dbID=dbID)
            r = {}
            for kind, equipmentType in (('artillery', SUPPORT_TYPE), ('inspire', BOOST_TYPE)):
                r[kind] = 'take' if perms.isEquipmentCommander(equipmentType) else 'give'
            rights[str(dbID)] = r
    except Exception:
        _logger.exception('role rights failed')
    return rights


def _setEquipmentCommander(dbID, kind):
    # same request as WG's context menu (UnitUserCMHandler.giveEquipmentCommander): dbID None = take
    # the role away; giving moves it from whoever had it (one player per role)
    from gui.prb_control.entities.stronghold.unit.ctx import GiveEquipmentCommanderCtx
    from gui.prb_control.items.stronghold_items import ARTILLERY_COMMANDER, INSPIRE_COMMANDER
    role = ARTILLERY_COMMANDER if kind == 'artillery' else INSPIRE_COMMANDER
    _sendRequest(GiveEquipmentCommanderCtx(dbID, role, 'prebattle/giveEquipmentCommander'))


def _divisionTip():
    # WG's divisionInfo tooltip (FortClanBattleRoom ⓘ -> TOOLTIPS_CONSTANTS.SORTIE_DIVISION): same data
    # as SortieDivisionTooltipData, labels from #tooltips:fortification/sortieDivisionToolTip/*
    try:
        if roomEntity() is None:
            return u''
        from gui.shared.tooltips import common, contexts
        result = common.SortieDivisionTooltipData(contexts.FortificationContext()).getDisplayableData()
        if not result or not result.get('divisions'):
            return u''
        d = result['divisions'][0]
        T = lambda key: _u(makeString('#tooltips:fortification/sortieDivisionToolTip/' + key))
        lines = [u'%s: %s' % (T('vehLevel'), _u(d.get('divisLevels', u''))),
                 u'%s: %s' % (T('playersLimit'), _u(d.get('divisPlayers', u''))),
                 u'%s: %s' % (T('legionnairesLimit'), _u(d.get('divisLegionnaires', u''))),
                 u'%s: %s' % (T('timeLimitSortie' if d.get('isSortie') else 'timeLimit'), _u(d.get('divisTime', u'')))]
        if d.get('dailyBonus'):
            lines.append(u'%s %s' % (_u(d['dailyBonus']), T('doublebonus')))
        return u'{HEADER}%s{/HEADER}{BODY}%s{/BODY}' % (_u(d.get('divisName', u'')), u'\n'.join(lines))
    except Exception:
        _logger.exception('division tooltip failed')
        return u''


# --- event progress reset (Clan -> Manoeuvres, "Fortschritt zuruecksetzen") ---------------------
# WG's event page (web_cache/wgshevents) sends PATCH /wgshevents/clan/reset_progress
# {"progress_stage": <current stage>} to the WGCG gateway. The client's own gateway accessor
# (IWebController.getWebRequester().data_source, used for wgsh_event_unfreeze_vehicle) carries the
# host and the session cookie, so the room uses it the same way. Texts are WG's web locale.
_AUTO_READY_WINDOW = 30.0  # s after coming back from the battle

_RESET_TEXTS = {
    'de': {
        "main_page.header_title": u"MAN\u00d6VER",
        "step_table.step": u"Abschnitt",
        "battle_control_buttons.is_disabled": u"Bis zum Start der Man\u00f6ver nicht verf\u00fcgbar.",
        "battle_control_buttons.reset_progress": u"FORTSCHRITT ZUR\u00dcCKSETZEN",
        "battle_control_buttons.reset_progress_text": u"Setzt den Fortschritt zum ersten Abschnitt zur\u00fcck, stellt alle Fahrzeuge der Clanmitglieder auf dienstbereit zur\u00fcck und liefert Reparaturteile. Vor dem Zur\u00fccksetzen angesammelte Reparaturteile verfallen.",
        "reset_progress_overlay_content.button_cancel": u"Abbrechen",
        "reset_progress_overlay_content.button_confirm": u"Zur\u00fccksetzen",
        "reset_progress_overlay_content.description_1": u"Aktueller Abschnitt: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Wenn Sie den Fortschritt f\u00fcr das Event zur\u00fccksetzen, kehrt Ihr Clan zum ersten Abschnitt zur\u00fcck und die Fahrzeuge aller Clanmitglieder sind wieder dienstbereit. <sparePartsHighlight>{spareParts}</sparePartsHighlight> Alle Reparaturteile verfallen dabei.",
        "reset_progress_overlay_content.description_2": u"Ihr Clan erh\u00e4lt Reparaturteile: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Fehler: Clanfortschritt f\u00fcr das Event wurde zur\u00fcckgesetzt.",
        "reset_progress_overlay_content.no_rights_notification": u"Aktion nicht m\u00f6glich. Unzureichende Befugnisse.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Aktion nicht m\u00f6glich. Sie sind kein Clanmitglied.",
        "reset_progress_overlay_content.successful_notification": u"Clanfortschritt wurde f\u00fcr das Event zur\u00fcckgesetzt.",
        "reset_progress_overlay_content.title": u"Fortschritt zur\u00fccksetzen?",
        "reset_progress_overlay_content.unknown_notification": u"Fehler: Vorgang kann nicht abgeschlossen werden.",
    },
    'en': {
        "main_page.header_title": u"MANEUVERS",
        "step_table.step": u"Stage",
        "battle_control_buttons.is_disabled": u"Unavailable until the start of Maneuvers.",
        "battle_control_buttons.reset_progress": u"RESET PROGRESS",
        "battle_control_buttons.reset_progress_text": u"Reset progress to return to the first Stage, restore all clan members' vehicles to duty, and receive Repair Parts. Repair Parts accumulated before the reset will be lost.",
        "reset_progress_overlay_content.button_cancel": u"Cancel",
        "reset_progress_overlay_content.button_confirm": u"Reset",
        "reset_progress_overlay_content.description_1": u"Current stage: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Once you reset progress in the event, your clan will return to the first stage, while all clan members' vehicles will be restored to duty. <sparePartsHighlight>{spareParts}</sparePartsHighlight> Repair Parts will be lost.",
        "reset_progress_overlay_content.description_2": u"Your clan will receive Repair Parts: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Error: Clan progress in the event has been reset.",
        "reset_progress_overlay_content.no_rights_notification": u"Action unavailable. Insufficient permissions.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Action unavailable. You are not a member of any clan.",
        "reset_progress_overlay_content.successful_notification": u"Clan progress in the event has been reset.",
        "reset_progress_overlay_content.title": u"Reset progress?",
        "reset_progress_overlay_content.unknown_notification": u"Error: Unable to complete action.",
    },
    'pl': {
        "main_page.header_title": u"MANEWRY",
        "step_table.step": u"Etap",
        "battle_control_buttons.is_disabled": u"Niedost\u0119pne do rozpocz\u0119cia manewr\u00f3w.",
        "battle_control_buttons.reset_progress": u"WYZERUJ POST\u0118PY",
        "battle_control_buttons.reset_progress_text": u"Wyzeruj post\u0119py, aby powr\u00f3ci\u0107 do pierwszego etapu, przywr\u00f3ci\u0107 pojazdy wszystkich cz\u0142onk\u00f3w klanu do s\u0142u\u017cby i otrzyma\u0107 cz\u0119\u015bci naprawcze. Cz\u0119\u015bci naprawcze zgromadzone przed wyzerowaniem zostan\u0105 utracone.",
        "reset_progress_overlay_content.button_cancel": u"Anuluj",
        "reset_progress_overlay_content.button_confirm": u"Wyzeruj",
        "reset_progress_overlay_content.description_1": u"Aktualny etap: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Po wyzerowaniu post\u0119p\u00f3w wydarzenia Tw\u00f3j klan powr\u00f3ci do pierwszego etapu, a pojazdy wszystkich cz\u0142onk\u00f3w klanu zostan\u0105 przywr\u00f3cone do s\u0142u\u017cby. <sparePartsHighlight>{spareParts}</sparePartsHighlight> Cz\u0119\u015bci naprawcze zostan\u0105 utracone.",
        "reset_progress_overlay_content.description_2": u"Tw\u00f3j klan otrzyma cz\u0119\u015bci naprawcze: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"B\u0142\u0105d: post\u0119py klanu w\u00a0wydarzeniu zosta\u0142y wyzerowane.",
        "reset_progress_overlay_content.no_rights_notification": u"Operacja niedost\u0119pna. Niewystarczaj\u0105ce uprawnienia.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Operacja niedost\u0119pna. Nie jeste\u015b cz\u0142onkiem \u017cadnego klanu.",
        "reset_progress_overlay_content.successful_notification": u"Post\u0119py klanu w wydarzeniu zosta\u0142y wyzerowane.",
        "reset_progress_overlay_content.title": u"Wyzerowa\u0107 post\u0119py?",
        "reset_progress_overlay_content.unknown_notification": u"B\u0142\u0105d: nie mo\u017cna doko\u0144czy\u0107 operacji.",
    },
    'cs': {
        "main_page.header_title": u"MAN\u00c9VRY",
        "step_table.step": u"F\u00e1ze",
        "battle_control_buttons.is_disabled": u"Nedostupn\u00e9 do za\u010d\u00e1tku Man\u00e9vr\u016f.",
        "battle_control_buttons.reset_progress": u"VYNULOVAT POSTUP",
        "battle_control_buttons.reset_progress_text": u"Vynulujte postup pro n\u00e1vrat k\u00a0prvn\u00ed f\u00e1zi, obnovte v\u0161echna vozidla \u010dlen\u016f klanu do slu\u017eby a\u00a0z\u00edskejte sou\u010d\u00e1sti na opravu. Sou\u010d\u00e1sti na opravu nahromad\u011bn\u00e9 p\u0159ed vynulov\u00e1n\u00edm budou ztraceny.",
        "reset_progress_overlay_content.button_cancel": u"Zru\u0161it",
        "reset_progress_overlay_content.button_confirm": u"Vynulovat",
        "reset_progress_overlay_content.description_1": u"Sou\u010dasn\u00e1 f\u00e1ze: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Jakmile vynulujete postup akc\u00ed, v\u00e1\u0161 klan se vr\u00e1t\u00ed do prvn\u00ed f\u00e1ze a z\u00e1rove\u0148 budou v\u0161echna vozidla \u010dlen\u016f klanu obnovena do slu\u017eby. Bude ztraceno <sparePartsHighlight>{spareParts}</sparePartsHighlight> sou\u010d\u00e1st\u00ed na opravu.",
        "reset_progress_overlay_content.description_2": u"V\u00e1\u0161 klan z\u00edsk\u00e1 sou\u010d\u00e1sti na opravu: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Chyba: Postup klanu akc\u00ed byl vynulov\u00e1n.",
        "reset_progress_overlay_content.no_rights_notification": u"Akce nen\u00ed k dispozici. Nedostate\u010dn\u00e1 opr\u00e1vn\u011bn\u00ed.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Akce nen\u00ed k dispozici. Nejste \u010dleny \u017e\u00e1dn\u00e9ho klanu.",
        "reset_progress_overlay_content.successful_notification": u"Postup klanu akc\u00ed byl vynulov\u00e1n.",
        "reset_progress_overlay_content.title": u"Vynulovat postup?",
        "reset_progress_overlay_content.unknown_notification": u"Chyba: Akci nelze dokon\u010dit.",
    },
    'fr': {
        "main_page.header_title": u"MAN\u0152UVRES",
        "step_table.step": u"\u00c9tape",
        "battle_control_buttons.is_disabled": u"Indisponible jusqu'au lancement de Man\u0153uvres.",
        "battle_control_buttons.reset_progress": u"R\u00c9INITIALISER LA PROGRESSION",
        "battle_control_buttons.reset_progress_text": u"R\u00e9initialiser la progression pour revenir \u00e0 la premi\u00e8re \u00c9tape, restaurer en service tous les v\u00e9hicules des membres du clan et recevoir des Pi\u00e8ces de r\u00e9paration. Les Pi\u00e8ces de r\u00e9paration accumul\u00e9es avant la r\u00e9initialisation seront perdues.",
        "reset_progress_overlay_content.button_cancel": u"Annuler",
        "reset_progress_overlay_content.button_confirm": u"R\u00e9initialiser",
        "reset_progress_overlay_content.description_1": u"\u00c9tape actuelle\u00a0: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Apr\u00e8s avoir r\u00e9initialis\u00e9 votre progression lors de l'\u00e9v\u00e8nement, votre clan retournera \u00e0 la premi\u00e8re \u00e9tape et tous les v\u00e9hicules des membres du clan seront restaur\u00e9s en service. <sparePartsHighlight>{spareParts}</sparePartsHighlight> Pi\u00e8ces de r\u00e9paration seront perdues.",
        "reset_progress_overlay_content.description_2": u"Votre clan recevra des Pi\u00e8ces de r\u00e9paration\u00a0: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Erreur\u00a0: la progression du clan dans l'\u00e9v\u00e8nement a \u00e9t\u00e9 r\u00e9initialis\u00e9e.",
        "reset_progress_overlay_content.no_rights_notification": u"Action indisponible. Droits insuffisants.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Action indisponible. Vous n'\u00eates pas membre d'un clan.",
        "reset_progress_overlay_content.successful_notification": u"La progression du clan lors de l'\u00e9v\u00e8nement a \u00e9t\u00e9 r\u00e9initialis\u00e9e.",
        "reset_progress_overlay_content.title": u"R\u00e9initialiser la progression\u00a0?",
        "reset_progress_overlay_content.unknown_notification": u"Erreur\u00a0: impossible de terminer cette action.",
    },
    'es': {
        "main_page.header_title": u"MANIOBRAS",
        "step_table.step": u"Etapa",
        "battle_control_buttons.is_disabled": u"No disponible hasta el inicio de Maniobras",
        "battle_control_buttons.reset_progress": u"REINICIAR PROGRESO",
        "battle_control_buttons.reset_progress_text": u"Reiniciar progreso para regresar a la primera etapa, volver a poner en servicio todos los veh\u00edculos de los miembros del clan y recibir piezas de repuesto. Las piezas de repuesto acumuladas antes del reinicio se perder\u00e1n.",
        "reset_progress_overlay_content.button_cancel": u"Cancelar",
        "reset_progress_overlay_content.button_confirm": u"Reiniciar",
        "reset_progress_overlay_content.description_1": u"Etapa actual: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Cuando reinicies el progreso del evento, tu clan regresar\u00e1 a la primera etapa y todos los veh\u00edculos de los miembros del clan se volver\u00e1n a poner en servicio. Se perder\u00e1n <sparePartsHighlight>{spareParts}</sparePartsHighlight>\u00a0piezas de repuesto.",
        "reset_progress_overlay_content.description_2": u"Tu clan recibir\u00e1 piezas de repuesto: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Error: Se ha reiniciado el progreso del clan en el evento.",
        "reset_progress_overlay_content.no_rights_notification": u"Acci\u00f3n no disponible. Permisos insuficientes.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Acci\u00f3n no disponible. No eres miembro de ning\u00fan clan.",
        "reset_progress_overlay_content.successful_notification": u"Se ha reiniciado el progreso del clan en el evento.",
        "reset_progress_overlay_content.title": u"\u00bfReiniciar progreso?",
        "reset_progress_overlay_content.unknown_notification": u"Error: no es posible completar la acci\u00f3n.",
    },
    'it': {
        "main_page.header_title": u"MANOVRE MILITARI",
        "step_table.step": u"Fase",
        "battle_control_buttons.is_disabled": u"Non disponibile fino all'inizio di Manovre militari.",
        "battle_control_buttons.reset_progress": u"AZZERA PROGRESSI",
        "battle_control_buttons.reset_progress_text": u"Azzera i progressi per tornare alla prima Fase, riportare in funzione tutti i veicoli dei membri del Clan e ricevere Pezzi di ricambio. I Pezzi di ricambio accumulati prima dell'azzeramento andranno perduti.",
        "reset_progress_overlay_content.button_cancel": u"Annulla",
        "reset_progress_overlay_content.button_confirm": u"Azzera",
        "reset_progress_overlay_content.description_1": u"Fase attuale: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Azzerando i progressi nell'evento, il tuo Clan torner\u00e0 alla prima fase, mentre tutti i veicoli dei membri del Clan saranno nuovamente rimessi in servizio. <sparePartsHighlight>{spareParts}</sparePartsHighlight> I Pezzi di ricambio andranno perduti.",
        "reset_progress_overlay_content.description_2": u"Il tuo Clan ricever\u00e0 Pezzi di ricambio: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Errore: i progressi di Clan nell'evento sono stati azzerati.",
        "reset_progress_overlay_content.no_rights_notification": u"Azione non disponibile. Permessi non sufficienti.",
        "reset_progress_overlay_content.not_in_clan_notification": u"Azione non disponibile. Non fai parte di un Clan.",
        "reset_progress_overlay_content.successful_notification": u"I progressi di Clan nell'evento saranno azzerati.",
        "reset_progress_overlay_content.title": u"Vuoi azzerare i progressi?",
        "reset_progress_overlay_content.unknown_notification": u"Errore: impossibile completare l'azione.",
    },
    'tr': {
        "main_page.header_title": u"TATB\u0130KAT",
        "step_table.step": u"A\u015fama",
        "battle_control_buttons.is_disabled": u"Tatbikat ba\u015flayana kadar ge\u00e7erli de\u011fildir.",
        "battle_control_buttons.reset_progress": u"GEL\u0130\u015e\u0130M\u0130 SIFIRLA",
        "battle_control_buttons.reset_progress_text": u"Geli\u015fimi s\u0131f\u0131rlayarak ilk A\u015famaya d\u00f6n\u00fcn, t\u00fcm klan \u00fcyelerinin ara\u00e7lar\u0131n\u0131 g\u00f6reve haz\u0131r hale getirin ve Tamir Par\u00e7alar\u0131 al\u0131n. S\u0131f\u0131rlamadan \u00f6nce biriktirilen Tamir Par\u00e7alar\u0131 kaybolacak.",
        "reset_progress_overlay_content.button_cancel": u"\u0130ptal",
        "reset_progress_overlay_content.button_confirm": u"S\u0131f\u0131rla",
        "reset_progress_overlay_content.description_1": u"Mevcut a\u015fama: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}Etkinlikte geli\u015fimi s\u0131f\u0131rlad\u0131\u011f\u0131n\u0131zda klan\u0131n\u0131z ilk a\u015famaya d\u00f6necek, t\u00fcm klan \u00fcyelerinin ara\u00e7lar\u0131 g\u00f6reve haz\u0131r hale gelecek. <sparePartsHighlight>{spareParts}</sparePartsHighlight> Tamir Par\u00e7as\u0131 kaybolacak.",
        "reset_progress_overlay_content.description_2": u"Klan\u0131n\u0131z \u015fu Tamir Par\u00e7alar\u0131n\u0131 alacak: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"Hata: Klan\u0131n etkinlikteki geli\u015fimi s\u0131f\u0131rland\u0131.",
        "reset_progress_overlay_content.no_rights_notification": u"\u0130\u015flem ge\u00e7ersiz. Yetersiz yetki.",
        "reset_progress_overlay_content.not_in_clan_notification": u"\u0130\u015flem ge\u00e7ersiz. Herhangi bir klan \u00fcyesi de\u011filsiniz.",
        "reset_progress_overlay_content.successful_notification": u"Klan\u0131n etkinlikteki geli\u015fimi s\u0131f\u0131rland\u0131.",
        "reset_progress_overlay_content.title": u"Geli\u015fim s\u0131f\u0131rlans\u0131n m\u0131?",
        "reset_progress_overlay_content.unknown_notification": u"Hata: \u0130\u015flem tamamlanam\u0131yor.",
    },
    'ru': {
        "main_page.header_title": u"\u041c\u0410\u041d\u0401\u0412\u0420\u042b",
        "step_table.step": u"\u042d\u0442\u0430\u043f",
        "battle_control_buttons.is_disabled": u"\u041d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0434\u043e \u043d\u0430\u0447\u0430\u043b\u0430 \u0441\u043e\u0431\u044b\u0442\u0438\u044f \u00ab\u041c\u0430\u043d\u0451\u0432\u0440\u044b\u00bb.",
        "battle_control_buttons.reset_progress": u"\u0421\u0411\u0420\u041e\u0421\u0418\u0422\u042c \u041f\u0420\u041e\u0413\u0420\u0415\u0421\u0421",
        "battle_control_buttons.reset_progress_text": u"\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441 \u0434\u043e \u043f\u0435\u0440\u0432\u043e\u0433\u043e \u044d\u0442\u0430\u043f\u0430, \u0447\u0442\u043e\u0431\u044b \u0432\u0435\u0440\u043d\u0443\u0442\u044c \u0432 \u0441\u0442\u0440\u043e\u0439 \u0442\u0435\u0445\u043d\u0438\u043a\u0443 \u0432\u0441\u0435\u0445 \u0438\u0433\u0440\u043e\u043a\u043e\u0432 \u043a\u043b\u0430\u043d\u0430 \u0438 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0440\u0435\u043c\u0440\u0435\u0441\u0443\u0440\u0441. \u041d\u0435\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0434\u043e \u0441\u0431\u0440\u043e\u0441\u0430 \u0440\u0435\u043c\u0440\u0435\u0441\u0443\u0440\u0441 \u0431\u0443\u0434\u0435\u0442 \u0441\u043f\u0438\u0441\u0430\u043d.",
        "reset_progress_overlay_content.button_cancel": u"\u041e\u0442\u043c\u0435\u043d\u0438\u0442\u044c",
        "reset_progress_overlay_content.button_confirm": u"\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c",
        "reset_progress_overlay_content.description_1": u"\u0422\u0435\u043a\u0443\u0449\u0438\u0439 \u044d\u0442\u0430\u043f: <progressStageHighlight>{progressStage}</progressStageHighlight>{lineBreak}\u041f\u043e\u0441\u043b\u0435 \u0441\u0431\u0440\u043e\u0441\u0430 \u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441\u0430 \u0432 \u0441\u043e\u0431\u044b\u0442\u0438\u0438 \u043a\u043b\u0430\u043d \u043f\u0435\u0440\u0435\u0439\u0434\u0451\u0442 \u043a \u043f\u0435\u0440\u0432\u043e\u043c\u0443 \u044d\u0442\u0430\u043f\u0443, \u0430 \u0442\u0435\u0445\u043d\u0438\u043a\u0430 \u0432\u0441\u0435\u0445 \u0438\u0433\u0440\u043e\u043a\u043e\u0432 \u043a\u043b\u0430\u043d\u0430 \u0432\u0435\u0440\u043d\u0451\u0442\u0441\u044f \u0432 \u0441\u0442\u0440\u043e\u0439. <sparePartsHighlight>{spareParts}</sparePartsHighlight> \u0435\u0434. \u043d\u0435\u0438\u0441\u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u043d\u043d\u043e\u0433\u043e \u0440\u0435\u043c\u0440\u0435\u0441\u0443\u0440\u0441\u0430 \u0431\u0443\u0434\u0435\u0442 \u0441\u043f\u0438\u0441\u0430\u043d\u043e.",
        "reset_progress_overlay_content.description_2": u"\u041a\u043b\u0430\u043d \u043f\u043e\u043b\u0443\u0447\u0438\u0442 \u0440\u0435\u043c\u0440\u0435\u0441\u0443\u0440\u0441: <sparePartsHighlight>{spareParts}</sparePartsHighlight>",
        "reset_progress_overlay_content.mismatch_progress_notification": u"\u041e\u0448\u0438\u0431\u043a\u0430: \u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441 \u043a\u043b\u0430\u043d\u0430 \u0432 \u0441\u043e\u0431\u044b\u0442\u0438\u0438 \u0443\u0436\u0435 \u0441\u0431\u0440\u043e\u0448\u0435\u043d.",
        "reset_progress_overlay_content.no_rights_notification": u"\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e. \u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u043f\u043e\u043b\u043d\u043e\u043c\u043e\u0447\u0438\u0439.",
        "reset_progress_overlay_content.not_in_clan_notification": u"\u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e. \u0412\u044b \u043d\u0435 \u0441\u043e\u0441\u0442\u043e\u0438\u0442\u0435 \u0432 \u043a\u043b\u0430\u043d\u0435.",
        "reset_progress_overlay_content.successful_notification": u"\u041f\u0440\u043e\u0433\u0440\u0435\u0441\u0441 \u043a\u043b\u0430\u043d\u0430 \u0432 \u0441\u043e\u0431\u044b\u0442\u0438\u0438 \u0441\u0431\u0440\u043e\u0448\u0435\u043d.",
        "reset_progress_overlay_content.title": u"\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441?",
        "reset_progress_overlay_content.unknown_notification": u"\u041e\u0448\u0438\u0431\u043a\u0430: \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043e\u0432\u0435\u0440\u0448\u0438\u0442\u044c \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435.",
    },
}

def _resetTexts():
    return _RESET_TEXTS.get(_lang()) or _RESET_TEXTS['en']


def _gateway():
    from skeletons.gui.web import IWebController
    webCtrl = dependency.instance(IWebController)
    requester = webCtrl.getWebRequester()
    source = getattr(requester, 'data_source', None)
    if source is None or not hasattr(source, '_request_data'):
        raise RuntimeError('no WGCG gateway (web controller state %r)' % (webCtrl.getStateID(),))
    return source


def _gatewayRequest(url, callback, method='GET', postData=None):
    # callback(ok, data): data = JSON answer, or WG's error data ({'title': ..., 'description': ...})
    def done(data, status, code, headers=None):
        # success: (data, http status, ResponseCodes.NO_ERRORS = 0); error: (error data, http, http)
        ok = code == 0 or (code is not None and 200 <= int(code) < 300)
        try:
            callback(ok, data if data is not None else {}, code)
        except Exception:
            _logger.exception('gateway callback %s failed', url)
    kwargs = {'method': method}
    if postData is not None:
        kwargs['post_data'] = postData
    _gateway()._request_data(done, url, **kwargs)


class _EventReset(object):
    # loads what WG's event page shows for its reset button: settings (roles, event dates),
    # the player's clan role, the clan's stage / repair parts / reward for the reset

    def __init__(self, onChanged):
        self._onChanged = onChanged
        self._raw = {}
        self._loading = 0
        self.info = None
        self.busy = False

    def load(self):
        self._raw = {}
        self._loading = 3
        for key, url in (('settings', '/wgshevents/settings'), ('account', '/wgshevents/account/info'),
                         ('clan', '/wgshevents/clan/info')):
            try:
                _gatewayRequest(url, self.__answer(key))
            except Exception:
                _logger.exception('event reset: request %s failed', url)
                self._loading -= 1

    def __answer(self, key):
        def answer(ok, data, code):
            self._raw[key] = data if ok else None
            if DEV:
                _logger.info('event reset: %s -> %s %s', key, code, json.dumps(data)[:1500])
            self._loading -= 1
            if self._loading <= 0:
                self.info = self.__build()
                _logger.info('event reset: %s', self.info and dict((k, v) for k, v in self.info.items() if k != 'texts'))
                self._onChanged()
        return answer

    def __build(self):
        settings = self._raw.get('settings') or {}
        account = self._raw.get('account') or {}
        clan = self._raw.get('clan') or {}
        config = settings.get('event_config') or {}
        if not config or not clan:
            if not DEV:
                return None
            self.devForced = True
            return {'visible': True, 'active': True, 'role': account.get('role'), 'stage': 0,
                    'spareParts': 0, 'reward': 0, 'busy': self.busy, 'texts': _resetTexts()}
        roles = config.get('reset_progress_roles') or []
        role = account.get('role')
        now = time.time()
        start, end = config.get('event_start_date') or 0, config.get('event_end_date') or 0
        texts = _resetTexts()
        visible = bool(account.get('clan_id')) and role is not None and role in roles
        active = bool(start and end and start <= now < end)
        # dev mode: show the box without the role (and outside the event) to check texts and layout;
        # "Reset" then makes no request, it only shows WG's "no rights" message
        self.devForced = bool(DEV) and not (visible and active)
        return {
            'visible': visible or bool(DEV),
            'active': active or bool(DEV),
            'role': role,
            'stage': clan.get('progress_stage') or 0,
            'spareParts': clan.get('spare_parts') or 0,
            'reward': (clan.get('current_stage') or {}).get('spare_parts_reward_for_reset') or 0,
            'busy': self.busy,
            'texts': texts,
        }

    def reset(self, done):
        # done(textKey): WG's notification text for the answer
        info = self.info
        if info is None or self.busy:
            return
        if getattr(self, 'devForced', False):
            _logger.info('event reset: dev box without rights, no request')
            done('reset_progress_overlay_content.no_rights_notification')
            return
        stage = info['stage']
        _logger.info('event reset: PATCH /wgshevents/clan/reset_progress progress_stage=%s', stage)
        self.busy = True
        info['busy'] = True
        self._onChanged()

        def answer(ok, data, code):
            self.busy = False
            _logger.info('event reset: answer %s %s', code, json.dumps(data)[:500])
            title = (data or {}).get('title') if not ok else None
            if ok:
                done('reset_progress_overlay_content.successful_notification')
            elif title == 'AccountNotInClan':
                done('reset_progress_overlay_content.not_in_clan_notification')
            elif title == 'AccountDoesNotHavePermissions':
                done('reset_progress_overlay_content.no_rights_notification')
            elif title == 'ClanProgressStageMismatch':
                done('reset_progress_overlay_content.mismatch_progress_notification')
            else:
                done('reset_progress_overlay_content.unknown_notification')
            self.load()
        _gatewayRequest('/wgshevents/clan/reset_progress', answer, method='PATCH', postData={'progress_stage': stage})


def _configureTips():
    # WG's tooltips of the configure (gear) button, enabled and disabled
    try:
        T = lambda key: _u(makeString('#tooltips:fortification/header/settingsBtn/' + key))
        return {'on': u'{HEADER}%s{/HEADER}{BODY}%s{/BODY}' % (T('header'), T('body')),
                'off': u'{HEADER}%s{/HEADER}{BODY}%s{/BODY}' % (T('disabled/header'), T('disabled/body'))}
    except Exception:
        _logger.exception('configure tooltips failed')
        return {}


def _frozenTips():
    # WG's tooltips of the frozen vehicle marker and the unfreeze button (SortieSlot.as)
    try:
        T = lambda key: _u(makeString(key))
        return {'icon': T(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_VEHBROKENICON),
                'btn': T(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_UNFROZEVEHICLEBTN),
                'btnOff': u'{HEADER}%s{/HEADER}{BODY}%s{/BODY}' % (
                    T(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_UNFROZEVEHICLEBTN_DISABLED_HEADER),
                    T(TOOLTIPS.FORTIFICATION_SORTIE_BATTLEROOM_UNFROZEVEHICLEBTN_DISABLED_BODY))}
    except Exception:
        _logger.exception('frozen tooltips failed')
        return {}


def _battleMapPoints(entity):
    # bases / control points of the current battle exactly as WG's direction tooltip has them
    # (ToolTipRefSysDirects.getDisplayableData -> mapPoints: x, y in 300 x 300 minimap units around
    # the centre, pointType 'base' (current battle) or 'control', color blue / red / empty, id)
    try:
        if not entity.isStrongholdSettingsValid():
            return None
        series = entity.getStrongholdSettings().getData().getHeader().getBattleSeriesStatus() or []
        current = [idx for idx, battle in enumerate(series) if battle.getCurrentBattle()]
        if not current:
            return None
        from gui.shared.tooltips import contexts, fortifications
        d = fortifications.ToolTipRefSysDirects(contexts.FortificationContext()).getDisplayableData(current[0]) or {}
        if not d.get('isMapEnabled'):
            return None
        return {'index': current[0], 'texture': _u(d.get('mapTexture', u'')),
                'points': [{'x': p['x'], 'y': p['y'], 'type': p['pointType'], 'color': p['color'], 'id': p['id']}
                           for p in d.get('mapPoints') or []]}
    except Exception:
        _logger.exception('battle map points failed')
        return None


def _arenaPoints(mapId, playerTeam):
    # WG's MinimapLobby.build without Flash: spawns, bases, control points of the arena in WG's
    # 300 x 300 minimap units around the centre (y up)
    import ArenaType
    arenaType = ArenaType.g_cache[int(mapId)]
    bottomLeft, upperRight = arenaType.boundingBox
    multX, multY = (upperRight - bottomLeft) / 300.0
    offset = (upperRight + bottomLeft) * 0.5
    norm = lambda x, y: ((x - offset.x) / multX, (y - offset.y) / multY)
    color = lambda team: 'blue' if team == playerTeam else 'red'
    points = []
    for team, spawns in enumerate(arenaType.teamSpawnPoints or (), 1):
        spawns = list(spawns or ())
        for number, point in enumerate(spawns, 1):
            x, y = norm(point[0], point[1])
            points.append({'x': x, 'y': y, 'type': 'spawn', 'color': color(team), 'id': number + 1 if len(spawns) > 1 else 1})
    for team, bases in enumerate(arenaType.teamBasePositions or (), 1):
        bases = list((bases or {}).values())
        for number, point in enumerate(bases, 2):
            x, y = norm(point[0], point[1])
            points.append({'x': x, 'y': y, 'type': 'base', 'color': color(team), 'id': number if len(bases) > 1 else 1})
    controls = list(arenaType.controlPoints or ())
    for number, point in enumerate(controls, 2):
        x, y = norm(point[0], point[1])
        points.append({'x': x, 'y': y, 'type': 'control', 'color': 'empty', 'id': number if len(controls) > 1 else 1})
    return points


def _mapIcon(mapID):
    # square top-down minimap (gui/maps/icons/map/<geometry>.png, 300x300); '' for a random map or
    # when the client has none for this map (map/stats/ are 500x235 landscape shots, not minimaps)
    if not mapID:
        return u''
    try:
        path = 'gui/maps/icons/map/%s.png' % getArenaGeometryName(mapID)
    except Exception:
        return u''
    try:
        import ResMgr
        if not ResMgr.isFile(path):
            _logger.info('no minimap %s', path)
            return u''
    except Exception:
        _logger.exception('minimap lookup failed')
    return u'img://' + path


def _me(entity):
    try:
        info = entity.getPlayerInfo()
        try:
            canChangeRoles = bool(entity.getPermissions().canChangeExtraEquipmentRole())
        except Exception:
            canChangeRoles = False
        return {'dbID': info.dbID, 'isCommander': info.isCommander(), 'isInSlot': info.isInSlot,
                'isReady': info.isReady, 'slotIdx': getattr(info, 'slotIdx', -1) if info.isInSlot else -1,
                'canChangeRoles': canChangeRoles}
    except Exception:
        _logger.exception('player info failed')
        return {}


def _packReserveOptions(entity, slotIndex):
    # same list as WG's FortReserveSelectPopover
    from gui.Scaleform.daapi.view.lobby.rally import vo_converters as rally_vo
    settings = entity.getStrongholdSettings()
    order = settings.getReserveOrder()
    if not 0 <= slotIndex < len(order):
        return None
    groupType = order[slotIndex]
    reserves = settings.getReserve()
    selected = [r.getId() for r in reserves.getSelectedReserves() if r]
    items = []
    for reserve in reserves.getUniqueReservesByGroupType(groupType):
        count = reserves.getReserveCount(reserve.getType(), reserve.getLevel())
        isSelected = reserve.getId() in selected
        try:
            bonus = u'' if reserve.isUsingInBattle() else u'+%s%%' % reserve.getBonusPercent()
        except Exception:
            bonus = u''
        items.append({'id': reserve.getId(),
                      'type': rally_vo.getReserveNameVO(reserve.getType()),
                      'title': _u(reserve.getTitle()),
                      'desc': _u(reserve.getDescription()),
                      'bonus': bonus,
                      'level': reserve.getLevel(),
                      'count': count - 1 if isSelected else count,
                      'selected': isSelected})
    return {'slot': slotIndex, 'title': _u(rally_vo.getReserveGroupTitle(groupType)), 'items': items}


def _actionButton(vo):
    # WG's ready button state; label is an i18n key ('#cyberSport:window/unit/ready')
    if not isinstance(vo, dict):
        return vo
    vo = dict(vo)
    try:
        for key in ('label', 'toolTipData'):
            value = vo.get(key)
            if isinstance(value, basestring) and value.startswith('#'):
                vo[key] = makeString(value)
    except Exception:
        _logger.exception('action button label failed')
    return vo


_GRID_SIZE = 207.0      # WG's MinimapGrid hit area (MinimapLobby.swf LobbyMinimapGrid.hitMc)
_GRID_POINT_LIFE = 5.0  # WG's MinimapClick animation: 140 frames, about 5 s, then it removes itself


# --- listener --------------------------------------------------------------------------
# One object registered with WG's prb dispatcher (IGlobalListener, like WG's room and window):
# it gets every entity callback and forwards it by name to the view.
_PRB_CALLBACKS = (
    'onUnitAutoSearchStarted', 'onUnitAutoSearchFinished', 'onUnitAutoSearchSuccess', 'onUnitFlagsChanged',
    'onUnitPlayerStateChanged', 'onUnitPlayerRolesChanged', 'onUnitPlayerOnlineStatusChanged',
    'onUnitPlayerBecomeCreator', 'onUnitPlayerNoLongerCreator', 'onUnitPlayerEnterOrLeaveArena',
    'onUnitRosterChanged', 'onUnitMembersListChanged', 'onUnitPlayerAdded', 'onUnitPlayerInfoChanged',
    'onUnitPlayerRemoved', 'onUnitPlayersListChanged', 'onUnitVehiclesChanged', 'onUnitPlayerVehDictChanged',
    'onUnitSettingChanged', 'onUnitRejoin', 'onUnitErrorReceived', 'onUnitExtraChanged', 'onUnitSizeChanged',
    'onUnitCurfewChanged', 'onUnitPlayerProfileVehicleChanged',
    'onUpdateHeader', 'onUpdateTimer', 'onUpdateState', 'onUpdateReserve', 'onStrongholdDataChanged',
    'onStrongholdOnReadyStateChanged', 'onStrongholdMaintenance', 'onCommanderIsReady',
    'onStrongholdDoBattleQueue', 'onPlayersMatching', 'onSlotVehileFiltersChanged', 'onEventFrozenVehiclesChanged',
    'onPrbEntitySwitching', 'onPrbEntitySwitched')


class _Listener(IGlobalListener):

    def __init__(self, view):
        super(_Listener, self).__init__()
        self._view = weakref.ref(view)


def _forward(name):
    def method(self, *args):
        view = self._view()
        if view is not None:
            view.onPrbCallback(name, args)
    method.__name__ = name
    return method


for _name in _PRB_CALLBACKS:
    setattr(_Listener, _name, _forward(_name))


class _ChatSink(object):
    # stands in for WG's Flash ChannelComponent / MinimapGrid on the unit chat controller
    # (LobbyLayout.setView): gets every formatted line and every unit chat command while active

    def __init__(self, view):
        self._view = weakref.ref(view)
        self._controller = lambda: None
        self.onDispose = Event.Event()
        self.alive = True

    def controller(self):
        return self._controller()

    def setController(self, controller):
        controller.activate()
        try:
            from messenger.gui import events_dispatcher
            events_dispatcher.notifyCarousel(controller.getChannel().getClientID(), notify=False)
        except Exception:
            _logger.exception('chat carousel notify failed')
        self._controller = weakref.ref(controller)
        view = self._view()
        if view is not None and self.alive:
            view.onChatController(controller)

    def removeController(self):
        self._controller = lambda: None

    def as_addMessageS(self, text):
        view = self._view()
        if view is not None and self.alive and text:
            view.onChatLine(text)

    def addCommand(self, command):
        view = self._view()
        if view is not None and self.alive:
            view.onChatCommand(command)

    def as_setJoinedS(self, flag):
        pass


class _PopoverShim(object):
    # EZ TANK PICKER reads the entity from a popover-like object (picker._frozenCDs)
    def __init__(self, entity):
        self.prbEntity = entity


# --- view ------------------------------------------------------------------------------

class EzRoomModel(ViewModel):
    __slots__ = ('onAction',)

    def __init__(self, properties=2, commands=1):
        super(EzRoomModel, self).__init__(properties=properties, commands=commands)

    def setData(self, value):
        self._setString(0, value)

    def setDev(self, value):
        self._setString(1, value)

    def _initialize(self):
        super(EzRoomModel, self)._initialize()
        self._addStringProperty('data', u'{}')
        self._addStringProperty('dev', u'')
        self.onAction = self._addCommand('onAction')


class EzRoomView(ViewImpl):

    def __init__(self, layoutID, state):
        settings = ViewSettings(layoutID, flags=ViewFlags.VIEW, model=EzRoomModel())
        super(EzRoomView, self).__init__(settings)
        self._state = state
        self._mode = 'panel' if (loadSettings().get('windowMode') == 'panel') else 'full'
        self._unitID = 0
        self._listener = None
        self._chat = None
        self._chatSeeding = False
        self._chatLines = []
        self._grid = []           # commander markings: {'x', 'y', 'time'} in WG's 207 px grid
        self._gridMap = 0
        self._speakEvents = {}    # dbID -> bool from g_messengerEvents.voip.onPlayerSpeaking
        self._highlight = []      # slots a dragged volunteer may go to (WG's getAvailableSlots)
        self._reserveSlot = -1    # reserve slot whose list is open
        self._parts = {}          # room data rebuilt on unit / stronghold events
        self._header = {}         # data from onUpdateHeader: direction, minimap, title
        self._room = None         # WG's FortClanBattleRoomVO (from the timer event)
        self._timer = None        # WG's ClanBattleTimerVO
        self._timerAt = 0.0
        self._timerEnd = None     # time.time() when the battle timer reaches 0 (change detection)
        self._enemyReady = False
        self._inQueue = False
        self._search = None       # enemy / legionnaire search panel (window auto search state)
        self._searchRef = None
        self._maintenance = False
        self._notice = None       # WG's leadership notice text (2.5 s)
        self._queueLock = False   # onStrongholdDoBattleQueue: configure + reserves off until flags change
        self._waitingShown = None
        self._dirty = False
        self._lastKey = None
        self._uiReady = False
        self._minimizing = False
        self._closing = False     # closed on purpose (ours or WG's signals), not by the game
        self._passive = None      # a WG Flash window opened from the room is up: panel hidden
        self._configureBrowserId = 0
        self._vehiclesInSlotFilters = {}
        self._candidatesDP = None
        self._finalized = False
        self._eventReset = _EventReset(self.__onEventResetChanged)

    @property
    def viewModel(self):
        return super(EzRoomView, self).getViewModel()

    def _getEvents(self):
        return ((self.viewModel.onAction, self.__onAction),)

    def canBeClosed(self):
        # only our own close / minimize / leave destroy the room window
        return False

    # life cycle ------------------------------------------------------------------------

    def _onLoading(self, *args, **kwargs):
        super(EzRoomView, self)._onLoading(*args, **kwargs)
        if DEV:
            self.viewModel.setDev(_devUI())
        try:
            self._start()
        except Exception:
            _logger.exception('starting the room failed, WG room instead')
            BigWorld.callback(0.0, lambda: self._fallback('start failed'))
            return
        BigWorld.callback(_READY_TIMEOUT, self.__checkReady)

    def _onLoaded(self, *args, **kwargs):
        super(EzRoomView, self)._onLoaded(*args, **kwargs)
        self._placeWindow()
        if DEV and _devFlag('simulateAutoReady'):
            # dev test: behave as if the player just came back from a stronghold battle
            _logger.info('auto ready: DEV simulation, acting as back from a battle')
            self._state['autoReady'] = {'since': None, 'tried': 0.0}
        try:
            self._eventReset.load()
        except Exception:
            _logger.exception('event reset: loading failed')

    def __onEventResetChanged(self):
        if not self._finalized:
            self._push()

    def __onEventResetDone(self, key):
        from gui import SystemMessages
        text = _resetTexts().get(key, key)
        ok = key.endswith('successful_notification')
        # WG's page: success = WARNING notification, errors = ERRORSIMPLE
        SystemMessages.pushMessage(text, type=SystemMessages.SM_TYPE.Warning if ok else SystemMessages.SM_TYPE.Error)

    def _start(self):
        entity = roomEntity()
        if entity is None:
            raise RuntimeError('no stronghold unit')
        self._unitID = entity.getID()
        session = self._state.get('session')
        if session is None or session.get('unitID') != self._unitID:
            # session counter: new room, new session
            self._state['session'] = {'unitID': self._unitID, 'battles': [], 'pending': {}, 'current': None}
        from gui.Scaleform.daapi.view.lobby.rally import rally_dps
        self._candidatesDP = rally_dps.SortieCandidatesLegionariesDP()
        self._listener = _Listener(self)
        _dispatcher().addListener(self._listener)
        self._listenAll(True)
        # chat: our sink takes the place of WG's Flash chat box on the unit channel controller
        from messenger.gui import events_dispatcher
        self._chat = _ChatSink(self)
        events_dispatcher.rqActivateChannel(_clientID(), self._chat)
        self._room = self._makeRoomVO(entity, 0, '', '', '', '', False, False, self._isSortie(entity))
        # same start as WG's room + window (_populate): replays of the current state to us
        entity.initEvents(self._listener)
        entity.updateStrongholdData()
        entity.forceTimerEvent()
        self._postMinimiseFilterUpdate(entity)
        self._validateNationGroup(entity)
        pInfo = entity.getPlayerInfo()
        if pInfo.isInSlot and not pInfo.isReady:
            entity.resetPlayerReadiness()
        try:
            from gui.prb_control.settings import SELECTOR_BATTLE_TYPES
            from gui.shared.utils import SelectorBattleTypesUtils as selectorUtils
            selectorUtils.setBattleTypeAsKnown(SELECTOR_BATTLE_TYPES.SORTIE)
        except Exception:
            _logger.exception('battle type known failed')
        from gui.prb_control.events_dispatcher import g_eventDispatcher
        from constants import PREBATTLE_TYPE
        g_eventDispatcher.hideUnitProgressInCarousel(PREBATTLE_TYPE.STRONGHOLD)
        _carouselOpenState(True)
        self._initSearchState(entity)
        self._showLeadershipNotification(entity)
        self._build()

    def _listenAll(self, on):
        # every (un)subscription is its own step: an error in one does not skip the others
        from CurrentVehicle import g_currentVehicle
        from gui.shared import events, g_eventBus
        from gui.shared.event_bus import EVENT_BUS_SCOPE
        from messenger.proto.events import g_messengerEvents
        from skeletons.gui.shared import IItemsCache
        from skeletons.account_helpers.settings_core import ISettingsCore
        bus = (g_eventBus.addListener if on else g_eventBus.removeListener)
        steps = [
            (bus, events.StrongholdEvent.STRONGHOLD_ON_TIMER, self.__onTimer, EVENT_BUS_SCOPE.STRONGHOLD),
            (bus, events.CoolDownEvent.PREBATTLE, self.__onCoolDown, EVENT_BUS_SCOPE.LOBBY),
            (bus, events.FightButtonEvent.FIGHT_BUTTON_UPDATE, self.__onAnyChange, EVENT_BUS_SCOPE.LOBBY),
            (bus, events.HideWindowEvent.HIDE_UNIT_WINDOW, self.__onHideUnitWindow, EVENT_BUS_SCOPE.LOBBY),
            # vehicle chosen in WG's selector or EZ TANK PICKER (both fire this, DEFAULT scope)
            (bus, events.CSVehicleSelectEvent.VEHICLE_SELECTED, self.__onVehicleSelected, None),
        ]
        for fn, name, handler, scope in steps:
            try:
                if scope is None:
                    fn(name, handler)
                else:
                    fn(name, handler, scope=scope)
            except Exception:
                _logger.exception('event bus %s %s failed', 'add' if on else 'remove', name)
        users = g_messengerEvents.users
        voip = g_messengerEvents.voip
        itemsCache = dependency.instance(IItemsCache)
        settingsCore = dependency.instance(ISettingsCore)
        wm = dependency.instance(IGuiLoader).windowsManager
        for owner, attr, handler in ((g_currentVehicle, 'onChanged', self.__onAnyChange),
                                     (itemsCache, 'onSyncCompleted', self.__onCacheResync),
                                     (users, 'onUsersListReceived', self.__onAnyChange),
                                     (users, 'onUserActionReceived', self.__onUserChange),
                                     (users, 'onUserStatusUpdated', self.__onAnyChange),
                                     (voip, 'onPlayerSpeaking', self.__onPlayerSpeaking),
                                     (settingsCore, 'onSettingsChanged', self.__onAnyChange),
                                     (wm, 'onWindowStatusChanged', self.__onWindowStatus)):
            try:
                event = getattr(owner, attr)
                if on:
                    event += handler
                else:
                    event -= handler
            except Exception:
                _logger.exception('%s %s failed', 'subscribing' if on else 'unsubscribing', attr)

    def _finalize(self):
        self._finalized = True
        self._hideWgTip()
        try:
            if self._listener is not None:
                dispatcher = _dispatcher()
                if dispatcher is not None:
                    dispatcher.removeListener(self._listener)
        except Exception:
            _logger.exception('removing the prb listener failed')
        self._listenAll(False)
        try:
            if self._chat is not None:
                self._chat.alive = False
                self._chat.onDispose(self._chat)
                if self._chat.controller() is not None:
                    from messenger.gui import events_dispatcher
                    events_dispatcher.rqDeactivateChannel(_clientID())
        except Exception:
            _logger.exception('chat deactivate failed')
        try:
            # same clean-up as WG's room (BaseRallyRoomView._dispose / StrongholdBattleRoom._dispose)
            from gui.shared import events, g_eventBus
            g_eventBus.handleEvent(events.HideWindowEvent(events.HideWindowEvent.HIDE_VEHICLE_SELECTOR_WINDOW))
            self._destroyFlashWindow('StrongholdSendInvitesWindow', alias=True)
            self._destroyConfigureWindow()
            _carouselOpenState(False)
            if self._minimizing and roomEntity() is not None:
                from gui.prb_control.events_dispatcher import g_eventDispatcher
                from constants import PREBATTLE_TYPE
                g_eventDispatcher.showUnitProgressInCarousel(PREBATTLE_TYPE.STRONGHOLD)
        except Exception:
            _logger.exception('room clean-up failed')
        if self._candidatesDP is not None:
            try:
                self._candidatesDP.fini()
            except Exception:
                pass
            self._candidatesDP = None
        state = self._state
        window = state.get('window')
        if window is not None and window.content in (None, self):
            state['window'] = None
        if self._minimizing:
            _logger.info('room minimized')
        elif self._closing or state.get('closing'):
            _logger.info('room window closed')
        elif roomEntity() is not None and self._uiReady:
            # destroyed by the game (0.8.2: opening the vehicle hub): back with the garage
            import traceback
            _logger.warning('room window closed by the game, it comes back with the garage:\n%s', ''.join(traceback.format_stack(limit=12)))
            armReopen(state)
        super(EzRoomView, self)._finalize()

    def _fallback(self, reason):
        fallback = self._state.get('fallback')
        if fallback is not None:
            fallback(reason)

    def __checkReady(self):
        if not self._finalized and not self._uiReady:
            _logger.error('room UI did not report back in %s s', _READY_TIMEOUT)
            self._fallback('ui not ready')

    def _placeWindow(self):
        window = self.getParentWindow()
        if window is None:
            return
        try:
            if self._mode == 'panel':
                pos = loadSettings().get('pos') or []
                x, y = (pos[0], pos[1]) if len(pos) == 2 else (100, 60)
                window.move(int(x), int(y))

        except Exception:
            _logger.exception('placing the room window failed')

    def minimize(self):
        # WG's minimize (StrongholdBattleRoomWindow.onWindowMinimize): room into the channel carousel
        self._minimizing = True
        window = self.getParentWindow()
        if window is not None:
            window.destroy()

    def close(self):
        self._closing = True
        window = self.getParentWindow()
        if window is not None:
            window.destroy()

    # prb callbacks ----------------------------------------------------------------------

    def onPrbCallback(self, name, args):
        if self._finalized:
            return
        try:
            handler = getattr(self, '_on_' + name, None)
            if handler is not None:
                handler(*args)
        except Exception:
            _logger.exception('%s failed', name)
        self.mark()

    def _on_onPrbEntitySwitched(self):
        entity = roomEntity()
        if entity is None or entity.getID() != self._unitID:
            _logger.info('room entity gone, closing the room window')
            BigWorld.callback(0.0, self.close)

    def _on_onUnitFlagsChanged(self, flags, timeLeft):
        self._queueLock = False
        if flags.isExternalLegionariesMatchingChanged() and not flags.isInExternalLegionariesMatching():
            from gui import SystemMessages
            from gui.impl import backport
            SystemMessages.pushMessage(backport.text(R.strings.system_messages.unit.warnings.EXTERNAL_LEGIONARIES_MATCHING_CANCELED()),
                                       type=SystemMessages.SM_TYPE.Warning)
        entity = roomEntity()
        if entity is not None:
            self._initSearchState(entity)

    def _on_onUnitPlayerAdded(self, pInfo):
        if not pInfo.isInvite():
            self._playerNotification('PLAYER_ADDED', pInfo)

    def _on_onUnitPlayerRemoved(self, pInfo):
        if not pInfo.isInvite():
            self._playerNotification('PLAYER_REMOVED', pInfo)

    def _on_onUnitPlayerOnlineStatusChanged(self, pInfo):
        self._playerNotification('PLAYER_OFFLINE' if pInfo.isOffline() else 'PLAYER_ONLINE', pInfo)

    def _on_onUnitPlayerRolesChanged(self, pInfo, pPermissions):
        entity = roomEntity()
        if entity is not None:
            entity.strongholdDataChanged()

    def _on_onUnitPlayerBecomeCreator(self, pInfo):
        if pInfo.isCurrentPlayer():
            entity = roomEntity()
            if entity is not None:
                self._showLeadershipNotification(entity)

    def _on_onUnitAutoSearchFinished(self):
        self._search = None

    def _on_onUnitRejoin(self):
        self._search = None

    def _on_onUnitErrorReceived(self, errorCode):
        pass

    def _on_onUpdateHeader(self, header, isFirstBattle, isUnitFreezed):
        entity = roomEntity()
        if entity is None:
            return
        self._updateMap(header)
        self._updateBuildings(entity)
        self._updateTitle(header)
        if self._room is not None:
            self._room['isBattleType'] = not header.isSortie()

    def _on_onStrongholdDataChanged(self, header, isFirstBattle, reserve, reserveOrder):
        entity = roomEntity()
        if entity is not None:
            self._initSearchState(entity)

    def _on_onStrongholdMaintenance(self, state):
        self._maintenance = bool(state)
        entity = roomEntity()
        if not state and entity is not None:
            self._updateBuildings(entity)
        self._updateUI()

    def _on_onStrongholdOnReadyStateChanged(self):
        self._updateUI()

    def _on_onStrongholdDoBattleQueue(self, isFirstBattle, readyButtonEnabled, reserveOrder):
        self._queueLock = not readyButtonEnabled

    def _on_onPlayersMatching(self, isPlayersMatchingInProgress):
        entity = roomEntity()
        if isPlayersMatchingInProgress and entity is not None:
            self._showPlayerSearch(entity)

    def __onAnyChange(self, *args, **kwargs):
        self.mark()

    def __onUserChange(self, *args):
        self.mark()

    def __onHideUnitWindow(self, event):
        self.close()

    def __onCoolDown(self, event):
        from gui.prb_control.settings import REQUEST_TYPE
        if getattr(event, 'requestID', None) == REQUEST_TYPE.SET_PLAYER_STATE:
            self.mark()

    def __onPlayerSpeaking(self, accountDBID, isSpeak):
        # same live event WG's voice chat manager forwards to Flash (as_onPlayerSpeakS)
        self._speakEvents[accountDBID] = bool(isSpeak)
        self.mark()

    def __onVehicleSelected(self, event):
        # BaseRallyRoomView.__onVehicleSelectHandler -> _selectVehicles
        items = event.ctx
        if items and roomEntity() is not None:
            from gui.prb_control.entities.base.unit.ctx import SetVehicleUnitCtx
            _sendRequest(SetVehicleUnitCtx(vTypeCD=items[0], waitingID='prebattle/change_settings'))

    def __onCacheResync(self, reason, diff):
        # BaseRallyRoomView._onCacheResync + StrongholdBattleRoom._onCacheResync (nation groups)
        self.mark()
        try:
            from gui.shared.gui_items import GUI_ITEM_TYPE
            from gui.shared.items_cache import CACHE_SYNC_REASON
            from nation_change.nation_change_helpers import iterVehTypeCDsInNationGroup, hasNationGroup
            from skeletons.gui.shared import IItemsCache
            entity = roomEntity()
            if entity is None or diff is None or GUI_ITEM_TYPE.VEHICLE not in diff:
                return
            items = dependency.instance(IItemsCache).items
            if reason == CACHE_SYNC_REASON.CLIENT_UPDATE:
                selected = self._selectedVehicles(entity)
                for cd in diff[GUI_ITEM_TYPE.VEHICLE]:
                    vehicle = items.getItemByCD(cd)
                    if selected and not vehicle.activeInNationGroup and selected[0] == cd:
                        self._selectVehicle(next(iterVehTypeCDsInNationGroup(vehicle.intCD)))
            mnVehs = dict((cd, items.getItemByCD(cd)) for cd in diff[GUI_ITEM_TYPE.VEHICLE] if hasNationGroup(cd))
            if mnVehs:
                from gui.prb_control.entities.base.external_battle_unit.base_external_battle_ctx import ChangeVehiclesInSlotFilterCtx
                for slotIndex, vehCDs in self._vehiclesInSlotFilters.items():
                    vehCDs = list(vehCDs or [])
                    for cd in list(vehCDs):
                        if cd in mnVehs and not mnVehs[cd].activeInNationGroup:
                            vehCDs[vehCDs.index(cd)] = next(iterVehTypeCDsInNationGroup(cd))
                    self._vehiclesInSlotFilters[slotIndex] = vehCDs
                    _sendRequest(ChangeVehiclesInSlotFilterCtx(slotIndex, vehCDs or [], waitingID='prebattle/change_settings'))
        except Exception:
            _logger.exception('cache resync failed')

    def __onWindowStatus(self, uniqueID, newStatus):
        # a WG Flash window opened from the room (invites, configure) went away: panel back
        passive = self._passive
        if passive is None:
            return
        try:
            count = _wgWindowCount(self._ownWindowID())
        except Exception:
            _logger.exception('counting windows failed')
            return
        if count > passive['baseline']:
            passive['seen'] = True
        elif passive['seen'] and count <= passive['baseline']:
            self._passive = None
            self._push(force=True)

    def _ownWindowID(self):
        window = self.getParentWindow()
        return window.uniqueID if window is not None else -1

    # helpers like WG's room / window ------------------------------------------------------

    @staticmethod
    def _isSortie(entity):
        try:
            if entity.isStrongholdSettingsValid():
                return entity.getStrongholdSettings().getHeader().isSortie()
        except Exception:
            pass
        return False

    @staticmethod
    def _makeRoomVO(entity, mapId, headerDescr, mineClanName, enemyClanName, waitForBattleDescr, isMapEnabled, isBattleTimerVisible, isSortie):
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        vo = vo_converters.makeFortClanBattleRoomVO(mapId, headerDescr, mineClanName, enemyClanName, waitForBattleDescr, isMapEnabled, isBattleTimerVisible, isSortie)
        vo['levelsRange'] = entity.getRosterSettings().getLevelsRange()
        return vo

    @staticmethod
    def _selectedVehicles(entity):
        return [vInfo.vehTypeCD for vInfo in entity.getVehiclesInfo() if not vInfo.isEmpty()]

    @staticmethod
    def _selectVehicle(vehTypeCD):
        from gui.prb_control.entities.base.unit.ctx import SetVehicleUnitCtx
        _sendRequest(SetVehicleUnitCtx(vTypeCD=vehTypeCD, waitingID='prebattle/change_settings'))

    def _postMinimiseFilterUpdate(self, entity):
        # StrongholdBattleRoom.__postMinimiseFilterUpdate: slot vehicle filters with nation-group fixes
        try:
            from nation_change.nation_change_helpers import iterVehTypeCDsInNationGroup, hasNationGroup
            from skeletons.gui.shared import IItemsCache
            from gui.prb_control.entities.base.external_battle_unit.base_external_battle_ctx import ChangeVehiclesInSlotFilterCtx
            items = dependency.instance(IItemsCache).items
            for slotIndex, data in (entity.getSlotFilters() or {}).items():
                vehCDs = list(data.get('vehicle_cds') or [])
                for cd in list(vehCDs):
                    if hasNationGroup(cd) and not items.getItemByCD(cd).activeInNationGroup:
                        vehCDs[vehCDs.index(cd)] = next(iterVehTypeCDsInNationGroup(cd))
                self._vehiclesInSlotFilters[slotIndex] = vehCDs
                _sendRequest(ChangeVehiclesInSlotFilterCtx(slotIndex, vehCDs, waitingID='prebattle/change_settings'))
        except Exception:
            _logger.exception('slot filter update failed')

    def _validateNationGroup(self, entity):
        # StrongholdBattleRoom.__validateNationGroup
        try:
            from nation_change.nation_change_helpers import iterVehTypeCDsInNationGroup
            from skeletons.gui.shared import IItemsCache
            selected = self._selectedVehicles(entity)
            if selected:
                vehicle = dependency.instance(IItemsCache).items.getItemByCD(selected[0])
                if not vehicle.activeInNationGroup:
                    self._selectVehicle(next(iterVehTypeCDsInNationGroup(vehicle.intCompactDescr)))
        except Exception:
            _logger.exception('nation group check failed')

    def _updateUI(self):
        try:
            from gui.prb_control.events_dispatcher import g_eventDispatcher
            g_eventDispatcher.updateUI()
        except Exception:
            _logger.exception('updateUI failed')

    def _playerNotification(self, key, pInfo):
        # StrongholdBattleRoomWindow.__addPlayerNotification: shown in the chat, not stored
        if pInfo.isCurrentPlayer():
            return
        try:
            from gui.prb_control import settings
            from gui.prb_control.formatters import messages
            text = messages.getUnitPlayerNotification(getattr(settings.UNIT_NOTIFICATION_KEY, key), pInfo)
            self._addChatLine(_u(text))
        except Exception:
            _logger.exception('player notification failed')

    def _showLeadershipNotification(self, entity):
        # BaseRallyMainWindow._showLeadershipNotification: WG's waiting text for 2.5 s
        try:
            if not entity.getShowLeadershipNotification():
                return
            from gui.impl import backport
            self._notice = _u(backport.text(R.strings.waiting.prebattle.giveLeadership()))
            self._push(force=True)

            def done():
                self._notice = None
                e = roomEntity()
                if e is not None:
                    e.doLeadershipNotificationShown()
                if not self._finalized:
                    self._push(force=True)

            BigWorld.callback(2.5, done)
        except Exception:
            _logger.exception('leadership notification failed')

    def _updateTitle(self, header):
        # StrongholdBattleRoom._updateTitle (WG's window title)
        from gui.Scaleform.locale.FORTIFICATIONS import FORTIFICATIONS
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        if header.isSortie():
            title = makeString(FORTIFICATIONS.STRONGHOLDTITLE_SORTIE)
        else:
            title = makeString(FORTIFICATIONS.STRONGHOLDTITLE_STRONGHOLD) % {'direction': vo_converters.getDirection(header.getDirection())}
            multiplier = header.getIndustrialResourceMultiplier()
            if multiplier > 1:
                title += ' (x%s)' % multiplier
        self._header['title'] = _u(title)

    def _updateMap(self, header):
        # StrongholdBattleRoom._updateMiniMapData: arena of the current battle, our team's colour
        currentBattle = header.getCurrentBattle()
        clan = header.getClan()
        mapId = 0
        points = []
        if currentBattle:
            mapId = currentBattle.getMapId()
            playerTeam = 1 if clan is not None and clan.getId() == currentBattle.getFirstClanId() else 2
            try:
                points = _arenaPoints(mapId, playerTeam) if mapId else []
            except Exception:
                _logger.exception('minimap points failed')
        if mapId != self._gridMap:
            self._grid = []  # MinimapGrid.setMapId clears the markings
        self._gridMap = mapId
        self._header['minimapPoints'] = points

    def _updateBuildings(self, entity):
        # StrongholdBattleRoom._updateBuildings: direction graphic (not for skirmishes)
        data = entity.getStrongholdSettings()
        if not (data.isValid() and data.getHeader() and not data.getHeader().isSortie()):
            return
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        header = data.getHeader()
        waitingForData = entity.isStrongholdUnitWaitingForData() or self._maintenance
        if not waitingForData:
            currentBattle = header.getCurrentBattle()
            enemyClan = header.getEnemyClan()
            if currentBattle is not None and enemyClan is not None:
                index = currentBattle.getIndex()
                attacker = currentBattle.getAttacker() != enemyClan.getId()
            else:
                index = None
                attacker = None
            self._header['direction'] = [vo_converters.makeDirectionVO(index, attacker, header.getBattleIdx()), entity.animationNotAvailable()]
        self._header['readyDirections'] = not waitingForData

    def _initSearchState(self, entity):
        # StrongholdBattleRoomWindow.__initState
        from gui.clans.clan_helpers import isLeaguesEnabled
        pInfo = entity.getPlayerInfo()
        if entity.isInQueue():
            if pInfo.isInSlot and not entity.canShowMaintenance():
                if isLeaguesEnabled():
                    # WG's own queue screen (separate lobby view), the room window goes away
                    from gui.prb_control.events_dispatcher import g_eventDispatcher
                    g_eventDispatcher.showStrongholdsBattleQueue()
                    BigWorld.callback(0.0, self.close)
                else:
                    self._setSearch(makeString(TOOLTIPS.STRONGHOLDS_TIMER_WAITINGFORDATA), 0, -1)
        elif entity.inPlayersMatchingMode():
            self._showPlayerSearch(entity)
        else:
            self._search = None

    def _showPlayerSearch(self, entity):
        # StrongholdBattleRoomWindow.__showPlayerSearchState
        if not entity.getPlayerInfo().isInSlot:
            return
        self._setSearch(makeString(TOOLTIPS.STRONGHOLDS_TIMER_LEGIONARIESSEARCH), entity.getSecondsCountInPlayersMatching(), 1)

    def _setSearch(self, label, seconds, direction):
        self._search = {'label': _u(label), 'seconds': max(0, int(seconds or 0)), 'dir': direction}
        self._searchRef = time.time() + direction * -1 * self._search['seconds']

    # chat --------------------------------------------------------------------------------

    def onChatController(self, controller):
        # history of the channel so far (formatted by WG); getHistory replays the server history
        # into the controller first, those lines would come to us twice
        self._chatSeeding = True
        try:
            self._chatLines = [_u(line) for line in list(controller.getHistory() or ())[-_CHAT_LINES:]]
        except Exception:
            _logger.exception('chat history failed')
        self._chatSeeding = False
        self.mark()

    def onChatLine(self, text):
        if not self._chatSeeding:
            self._addChatLine(_u(text))

    def _addChatLine(self, text):
        self._chatLines.append(text)
        if len(self._chatLines) > _CHAT_LINES:
            del self._chatLines[:-_CHAT_LINES]
        self.mark()

    def onChatCommand(self, command):
        # MinimapGrid.addCommand: commander marking (unit chat ATTENTIONTOCELL)
        try:
            if command.isOnMinimap():
                now = time.time()
                self._grid = [p for p in self._grid if now - p['time'] < _GRID_POINT_LIFE]
                self._grid.append({'x': command.getMapPosX(), 'y': command.getMapPosY(), 'time': now})
                self._push(force=True)
        except Exception:
            _logger.exception('chat command failed')

    def _packChat(self):
        controller = self._chat.controller() if self._chat is not None else None
        try:
            joined = bool(controller.isJoined()) if controller is not None else False
        except Exception:
            joined = False
        return {'joined': joined, 'lines': self._chatLines}

    # building the data -----------------------------------------------------------------------

    def mark(self):
        # many callbacks arrive in a burst: rebuild once on the next tick
        if self._dirty or self._finalized:
            return
        self._dirty = True
        BigWorld.callback(0.0, self._flush)

    def _flush(self):
        self._dirty = False
        if not self._finalized:
            self._build()

    def _build(self):
        entity = roomEntity()
        if entity is None:
            return
        from gui.Scaleform.daapi.view.lobby.fortifications.vo_converters import makeStrongholdsSlotsVOs, makeSortieVO
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        p = dict(self._parts)

        def part(name, fn):
            try:
                p[name] = fn()
            except Exception:
                _logger.exception('room data %s failed', name)

        valid = entity.isStrongholdSettingsValid()
        header = entity.getStrongholdSettings().getHeader() if valid else None
        maxPlayers = header.getMaxPlayersCount() if header is not None else vo_converters.MAX_PLAYER_COUNT_ALL
        perms = entity.getPermissions()
        part('rally', lambda: makeSortieVO(entity, perms.canChangeUnitState(), unitMgrID=entity.getID(),
                                           canInvite=perms.canSendInvite(), maxPlayerCount=maxPlayers))
        if valid:
            part('slots', lambda: list(makeStrongholdsSlotsVOs(entity, entity.getID(), maxPlayerCount=maxPlayers)[1]))
            part('tableHeader', lambda: self._tableHeader(entity, maxPlayers, header.getMaxLegionariesCount()))
            part('reserves', lambda: self._reserves(entity, p))
            part('opened', lambda: list(vo_converters.makeOpenRoomButtonVO(entity.getStrongholdSettings().getState().getPublic())))
        part('actionButton', lambda: self._actionButtonState(entity))
        part('candidates', lambda: self._candidates(entity))
        part('configure', lambda: self._configureState(entity))
        part('comment', lambda: _u(entity.getCensoredComment() or u''))
        part('me', lambda: _me(entity))
        part('roleRights', lambda: _roleRights(entity, p.get('slots') or []))
        part('readyCoolDown', lambda: self._readyCoolDown())
        part('back', lambda: _backLink(entity))
        part('gridEnabled', lambda: bool(perms.canChangeUnitState() and not (entity.isStrongholdUnitFreezed() or entity.isStrongholdUnitWaitingForData())))
        part('battleMap', lambda: _battleMapPoints(entity))
        part('divisionTip', _divisionTip)
        part('directTips', lambda: bool(valid))
        try:
            self._inQueue = bool(entity.getFlags().isInQueue())
            enemy = header.getEnemyClan() if header is not None else None
            self._enemyReady = bool(enemy.getReadyStatus()) if enemy is not None else False
        except Exception:
            _logger.exception('ready status failed')
        # WG's waiting animation while the stronghold data is not valid (showStrongholdWaiting)
        if self._waitingShown is not None and self._waitingShown != (not valid):
            self._updateUI()
        self._waitingShown = not valid
        self._parts = p
        self._push()

    @staticmethod
    def _tableHeader(entity, maxPlayers, maxLegionaries):
        # StrongholdBattleRoom._updateTableHeader
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        pCount = lCount = 0
        for slotInfo in entity.getUnitFullData().slotsIterator:
            if slotInfo.player is not None:
                pCount += 1
                if slotInfo.player.isLegionary():
                    lCount += 1
        return vo_converters.makeTableHeaderVO(pCount, maxPlayers, lCount, maxLegionaries)

    def _reserves(self, entity, parts):
        # StrongholdBattleRoom._updateReserves / __updateReserve
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        from gui.prb_control.items.stronghold_items import REQUISITION_TYPE
        settings = entity.getStrongholdSettings()
        reserveData = settings.getReserve()
        selected = reserveData.getSelectedReserves()
        havePermissions = entity.getPermissions().canChangeConsumables()
        isInBattle = entity.getFlags().isInArena()
        slots, enabled = [], []
        for index, groupType in enumerate(settings.getReserveOrder()):
            group = reserveData.getUniqueReservesByGroupType(groupType)
            current = None
            for reserve in group:
                if reserve in selected:
                    current = reserve
                    break
            disabledByRequisition = groupType == REQUISITION_TYPE and not entity.isFirstBattle()
            empty = len(group) == 0
            tooltip, tooltipType = vo_converters.makeReserveSlotTooltipVO(current, groupType, empty, havePermissions, isInBattle, disabledByRequisition)
            slots.append(vo_converters.makeReserveSlotVO(current.getType() if current else None, groupType,
                                                         current.getId() if current else 0, current.getLevel() if current else 0,
                                                         index, tooltip, tooltipType))
            enabled.append(bool(havePermissions and not empty and not isInBattle and not disabledByRequisition and not self._queueLock))
        parts['reservesEnabled'] = enabled
        return slots

    def _configureState(self, entity):
        # StrongholdBattleRoom._updateConfigureButtonState
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        if not entity.isStrongholdSettingsValid():
            return self._parts.get('configure')
        flags = entity.getFlags()
        readyEnabled = not entity.isStrongholdUnitFreezed() and not self._queueLock
        isEnabled = readyEnabled and entity.isFirstBattle() and not flags.isInQueue() and not flags.isInArena()
        return vo_converters.makeConfigureButtonVO(isEnabled, True)

    @staticmethod
    def _actionButtonState(entity):
        # StrongholdBattleRoom._setActionButtonState (only while the unit is active)
        from gui.Scaleform.daapi.view.lobby.prb_windows.stronghold_action_button_state_vo import StrongholdActionButtonStateVO
        from gui.prb_control.settings import FUNCTIONAL_FLAG
        flags = entity.getFunctionalFlags()
        if not (flags & FUNCTIONAL_FLAG.UNIT and flags & FUNCTIONAL_FLAG.STRONGHOLD):
            return None
        return _actionButton(dict(StrongholdActionButtonStateVO(entity)))

    def _candidates(self, entity):
        # WG's waiting list data provider (SortieCandidatesLegionariesDP), without Flash
        dp = self._candidatesDP
        dp.buildList(entity.getCandidates())
        return list(dp.collection)

    @staticmethod
    def _readyCoolDown():
        from gui.prb_control.entities.base.cooldown import getPrbRequestCoolDown
        from gui.prb_control.settings import REQUEST_TYPE
        return max(0.0, float(getPrbRequestCoolDown(REQUEST_TYPE.SET_PLAYER_STATE) or 0))

    def _packGrid(self, now):
        points = [{'x': p['x'] / _GRID_SIZE, 'y': p['y'] / _GRID_SIZE, 'left': _GRID_POINT_LIFE - (now - p['time']), 't': p['time']}
                  for p in self._grid if now - p['time'] < _GRID_POINT_LIFE]
        return {'points': points, 'clickEnabled': bool(self._parts.get('gridEnabled')) and bool(self._gridMap)}

    def _sessionInfo(self, room):
        # session counter (battles, win rate, durations), skirmish rooms only (not Advances)
        if room.get('isBattleType') is not False:
            return None
        session = self._state.get('session') or {}
        battles = session.get('battles') or []
        wins = len([b for b in battles if b['result'] > 0])
        durations = [b['duration'] for b in battles if b.get('duration')]
        return {'battles': len(battles), 'wins': wins,
                'winrate': int(round(100.0 * wins / len(battles))) if battles else None,
                'avg': int(round(sum(durations) / len(durations))) if durations else None,
                'total': int(round(sum(durations))) if durations else None}

    def _waitingText(self):
        if not self._waitingShown:
            return None
        text = _u(makeString('#waiting:prebattle/change_settings'))
        return text if text and not text.startswith(u'#') else u'…'

    def _maintenanceInfo(self):
        if not self._maintenance:
            return None
        from gui.Scaleform.locale.FORTIFICATIONS import FORTIFICATIONS
        return {'header': _u(makeString(FORTIFICATIONS.MAINWINDOW_MAINTENANCE_HEADER)),
                'body': _u(makeString(FORTIFICATIONS.MAINWINDOW_MAINTENANCE_BODY)),
                'button': _u(makeString(FORTIFICATIONS.MAINWINDOW_MAINTENANCE_BUTTON))}

    def _searchInfo(self):
        search = self._search
        if search is None:
            return None
        entity = roomEntity()
        canCancel = False
        try:
            canCancel = bool(entity.getPermissions().canStopBattleQueue()) if entity is not None else False
        except Exception:
            _logger.exception('search permissions failed')
        seconds = max(0, int(round((time.time() - self._searchRef) if search['dir'] > 0 else (self._searchRef - time.time()))))
        return dict(search, seconds=seconds, canCancel=canCancel)

    def _pack(self):
        now = time.time()
        p = self._parts
        slots = p.get('slots') or []
        candidates = p.get('candidates') or []
        room = self._room or {}
        settings = loadSettings()
        data = {
            'version': __version__,
            'lang': _lang(),
            'dev': bool(DEV),
            'mode': self._mode,
            'pos': settings.get('pos'),
            'title': self._header.get('title', u''),
            'back': p.get('back') or {},
            'divisionTip': p.get('divisionTip', u''),
            'configureTips': _configureTips(),
            'frozenTips': _frozenTips(),
            'directTips': p.get('directTips', False),
            'battleMap': p.get('battleMap'),
            'me': p.get('me') or {},
            'room': room,
            'mapIcon': _mapIcon(room.get('mapID')),
            'minimapPoints': self._header.get('minimapPoints') or [],
            'grid': self._packGrid(now),
            'rally': p.get('rally') or {},
            'slots': slots,
            'candidates': candidates,
            'speaking': _speaking(slots, candidates, self._speakEvents),
            'roleRights': p.get('roleRights') or {},
            'tableHeader': p.get('tableHeader') or [],
            'timer': self._timer,
            'timerAge': now - self._timerAt if self._timer else 0,
            'readyStatus': [self._inQueue, self._enemyReady],
            'readyDirections': self._header.get('readyDirections'),
            'direction': self._header.get('direction'),
            'reserves': p.get('reserves') or [],
            'reservesEnabled': p.get('reservesEnabled') or [],
            'opened': p.get('opened'),
            'configure': p.get('configure'),
            'actionButton': p.get('actionButton'),
            'readyCoolDown': p.get('readyCoolDown', 0),
            'comment': p.get('comment', u''),
            'vehiclesTitle': None,
            'highlight': self._highlight,
            'chat': self._packChat(),
            'waiting': self._waitingText(),
            'maintenance': self._maintenanceInfo(),
            'search': self._searchInfo(),
            'notice': self._notice,
            'passive': self._passive is not None,
            'session': self._sessionInfo(room),
            'reserveOptions': None,
            'eventReset': self._eventReset.info,
            'autoReady': bool(settings.get('autoReady', False)),
            'settings': settings,
        }
        if self._reserveSlot >= 0:
            entity = roomEntity()
            try:
                data['reserveOptions'] = _packReserveOptions(entity, self._reserveSlot) if entity is not None else None
            except Exception:
                _logger.exception('reserve options failed')
        if DEV:
            data['raw'] = {'calls': dict(self._parts, header=self._header), 'slotCalls': {}}
        return _clean(data)

    def _autoReady(self):
        # own extension: back from a stronghold battle, set the player ready once, like his own
        # click on "Ready" (WG's togglePlayerReadyAction, only own slot - WG has no ready for others)
        pending = self._state.get('autoReady')
        if not pending or self._finalized:
            return
        if not loadSettings().get('autoReady', False):
            self._state['autoReady'] = None
            return
        entity = roomEntity()
        if entity is None:
            return
        try:
            now = time.time()
            if entity.getFlags().isInArena() or entity.getPlayerInfo().isInArena():
                return
            if pending['since'] is None:
                pending['since'] = now
            if now - pending['since'] > _AUTO_READY_WINDOW:
                _logger.info('auto ready: gave up (%s s)', _AUTO_READY_WINDOW)
                self._state['autoReady'] = None
                return
            info = entity.getPlayerInfo()
            if info.isReady or info.isCommander():
                # the commander presses his button himself (reset, then into the battle)
                self._state['autoReady'] = None
                return
            if now - pending['tried'] < 2.0 or self._readyCoolDown() > 0:
                return
            result = entity.canPlayerDoAction()
            if not getattr(result, 'isValid', result):
                reason = getattr(result, 'restriction', result)
                if pending.get('reason') != reason:
                    pending['reason'] = reason
                    _logger.info('auto ready: waiting, WG says %r', reason)
                return
            pending['tried'] = now
            _logger.info('auto ready: setting the player ready after the battle')
            entity.togglePlayerReadyAction(False)
        except Exception:
            _logger.exception('auto ready failed')
            self._state['autoReady'] = None

    def _push(self, force=False):
        # sends the data to the web UI, only when it changed (the timer and the search seconds
        # count in the UI itself; they only count as a change when they jump)
        if self._finalized:
            return
        self._autoReady()
        try:
            data = self._pack()
            keyData = dict(data, timer=bool(data['timer']), timerAge=None, readyCoolDown=None,
                           search=dict(data['search'], seconds=None) if data['search'] else None,
                           grid=dict(data['grid'], points=[(pt['x'], pt['y'], pt['t']) for pt in data['grid']['points']]))
            key = json.dumps(keyData, sort_keys=True)
            if key == self._lastKey and not force:
                return
            self._lastKey = key
            self.viewModel.setData(json.dumps(data))
        except Exception:
            _logger.exception('packing room data failed')
            return
        if DEV and not getattr(self, '_snapshotPending', False):
            self._snapshotPending = True
            BigWorld.callback(2.0, self._writeSnapshot)

    def _writeSnapshot(self):
        # dev only: last room state as a file, used by the browser preview harness
        self._snapshotPending = False
        if self._finalized:
            return
        try:
            path = os.path.dirname(_SNAPSHOT_FILE)
            if not os.path.isdir(path):
                os.makedirs(path)
            with open(_SNAPSHOT_FILE, 'wb') as f:
                f.write(json.dumps(self._pack(), indent=1, sort_keys=True).encode('utf-8'))
        except Exception:
            _logger.exception('writing snapshot failed')

    # battle timer (StrongholdEvent.STRONGHOLD_ON_TIMER, once per second) ---------------------

    def __onTimer(self, event):
        try:
            self._onTimer(event.ctx)
        except Exception:
            _logger.exception('timer event failed')
        self._autoReady()

    def _onTimer(self, data):
        # StrongholdBattleRoom._onMatchmakingTimerChanged + StrongholdBattleRoomWindow._onMatchmakingTimerChanged
        from gui import GUI_SETTINGS, makeHtmlString
        from gui.impl import backport
        from gui.Scaleform.daapi.view.lobby.rally import vo_converters
        from gui.Scaleform.locale.CYBERSPORT import CYBERSPORT
        from gui.Scaleform.locale.FORTIFICATIONS import FORTIFICATIONS
        from helpers import int2roman, time_utils
        entity = roomEntity()
        if entity is None:
            return
        now = time.time()
        isBattleTimerVisible = False
        wfbDescr = None
        playerClanName = None
        enemyClanName = None
        currentBattle = data['currentBattle']
        mapId = currentBattle.getMapId() if currentBattle else 0
        enemyClanData = data['enemyClan']
        enemyVisible = enemyClanData is not None
        isInBattle = entity.getFlags().isInArena()
        textid = data['textid']
        level = int2roman(data['maxLevel'])
        timer = None
        if data['isSortie']:
            headerDescr = makeString(FORTIFICATIONS.STRONGHOLDINFO_SORTIE) % {'level': level}
            timetext = None
            if textid in (FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_ENDOFBATTLESOON, FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLESOON):
                timetext = makeHtmlString('html_templates:lobby/fortifications/introView', 'fortBattles', {'text': time_utils.getTimeLeftFormat(data['dtime'])})
            elif textid in (FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLETOMORROW, FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLETODAY):
                timetext = makeHtmlString('html_templates:lobby/fortifications/introView', 'fortBattles', {'text': backport.getShortTimeFormat(data['peripheryStartTimestamp'])})
            wfbDescr = makeString(textid, nextDate=timetext)
        else:
            headerDescr = makeString(FORTIFICATIONS.STRONGHOLDINFO_STRONGHOLD) % {'direction': vo_converters.getDirection(data['direction'])}
            if textid != FORTIFICATIONS.ROSTERINTROWINDOW_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLESOON:
                timetext = None
                if textid in (FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLETOMORROW, FORTIFICATIONS.SORTIE_INTROVIEW_FORTBATTLES_NEXTTIMEOFBATTLETODAY):
                    timetext = makeHtmlString('html_templates:lobby/fortifications/introView', 'fortBattles', {'text': backport.getShortTimeFormat(data['matchmakerNextTick'])})
                wfbDescr = makeString(textid, nextDate=timetext)
            else:
                isBattleTimerVisible = True
                fontColors = GUI_SETTINGS.lookup('StrongholdsTimerColors') or {}
                colorRegular = fontColors.get('regular', '#FFDD99')
                colorAlarm = fontColors.get('alarm', '#ff7f00')
                enemyClanName = '?'
                if enemyVisible:
                    clColor = enemyClanData.getColor()
                    clColor = '#%06x' % clColor if clColor else '#ffffff'
                    enemyClanName = "<b><font face='$FieldFont' color='{0}'>[{1}]</font></b>".format(clColor, enemyClanData.getTag())
                clan = data['clan']
                if clan:
                    clColor = clan.getColor()
                    clColor = '#%06x' % clColor if clColor else '#ffffff'
                    playerClanName = "<b><font face='$FieldFont' color='{0}'>[{1}]</font></b>".format(clColor, clan.getTag())
                dtime = data['dtime'] if not isInBattle else 0
                timer = vo_converters.makeClanBattleTimerVO(dtime, "<font face='$FieldFont' size='18' color='{0}'>###</font>".format(colorRegular),
                                                            "<font face='$FieldFont' size='18' color='{0}'>###</font>".format(colorAlarm),
                                                            0xBB6200, 0xBB2B00, '00', 0 if data['isFirstBattle'] else 1)
                # WG's alarm sound (FortClanBattleRoom.onTimerAlert): every second of the last 10
                if 0 < dtime <= 10:
                    try:
                        from gui.Scaleform.daapi.view.lobby.strongholds.sound_controller import g_strongholdSoundController
                        g_strongholdSoundController.playBattleRoomTimerAlert()
                    except Exception:
                        _logger.exception('timer alert sound failed')
        room = self._makeRoomVO(entity, mapId, headerDescr, playerClanName, enemyClanName, wfbDescr, enemyVisible, isBattleTimerVisible, data['isSortie'])
        if data['forceUpdateBuildings']:
            self._updateBuildings(entity)
        # search panel time (window): count down while the squad waits in the queue, else up
        if self._search is not None and entity.isInQueue() and entity.getPlayerInfo().isInSlot:
            if data['dtime'] > 0 and textid == TOOLTIPS.STRONGHOLDS_TIMER_SQUADINQUEUE:
                self._setSearch(makeString(CYBERSPORT.WINDOW_AUTOSEARCH_SEARCHENEMY_MAINTEXT), data['dtime'], -1)
            else:
                startTimer = 0
                _, unit = entity.getUnit()
                timestamp = unit.getModalTimestamp() if unit else 0
                if timestamp:
                    startTimer = max(0, int(time_utils.getCurrentTimestamp() - time_utils.makeLocalServerTime(timestamp)))
                label = TOOLTIPS.STRONGHOLDS_TIMER_SEARCHENEMY if data['isSortie'] or data['isFirstBattle'] else CYBERSPORT.WINDOW_AUTOSEARCH_SEARCHENEMY_MAINTEXT
                self._setSearch(makeString(label), startTimer, 1)
        timerEnd = (now + timer['deltaTime']) if timer is not None else None
        jumped = (timerEnd is None) != (self._timerEnd is None) or (timerEnd is not None and abs(timerEnd - self._timerEnd) >= 1.0)
        self._room = room
        self._timer = timer
        if jumped:
            self._timerAt = now
            self._timerEnd = timerEnd
        elif timer is not None:
            # keep the reference the UI counts from; deltaTime matching it
            timer['deltaTime'] = max(0, self._timerEnd - self._timerAt)
        self._push(force=jumped)

    # actions ---------------------------------------------------------------------------------

    def __onAction(self, args=None):
        args = args or {}
        action = args.get('action')
        try:
            self._action(action, args)
        except Exception:
            _logger.exception('action %r failed', args)

    def _action(self, action, args):
        entity = roomEntity()
        from gui.prb_control.entities.base.unit.ctx import AssignUnitCtx, KickPlayerUnitCtx, ChangeOpenedUnitCtx
        if action == 'uiReady':
            if not self._uiReady:
                self._uiReady = True
                _logger.info('room UI ready (%s mode)', self._mode)
            self._placeWindow()
            self._push(force=True)
        elif action == 'log':
            _logger.info('ui: %s', args.get('msg'))
        elif action == 'minimize':
            self.minimize()
        elif action == 'close':
            if self._search is None:
                _leave(True)
        elif action == 'back':
            _leave(False)
        elif action == 'wgRoom':
            # fallback on purpose: WG's own room for this room (the mods list brings EZ ROOM back)
            self._fallback('user')
        elif action == 'autoReady':
            settings = loadSettings()
            settings['autoReady'] = not settings.get('autoReady', False)
            saveSettings(settings)
            self._push(force=True)
        elif action == 'savePos':
            settings = loadSettings()
            settings['pos'] = [int(args.get('x') or 0), int(args.get('y') or 0)]
            saveSettings(settings)
        elif action == 'moveTo':
            # panel mode only: our small window follows the mouse while the title bar is dragged
            window = self.getParentWindow()
            if window is not None:
                window.move(int(args.get('x') or 0), int(args.get('y') or 0))
        elif action == 'wgTip':
            self._showWgTip(args.get('kind'), int(args.get('index') or 0))
        elif action == 'wgTipHide':
            self._hideWgTip()
        elif action == 'sort':
            settings = loadSettings()
            name = 'candSort' if args.get('target') == 'cand' else 'sort'
            settings[name] = {'key': args.get('key') or u'', 'dir': int(args.get('dir') or 0)}
            saveSettings(settings)
        elif action == 'copyLink':
            url = args.get('url') or u''
            if url:
                BigWorld.wg_copyToClipboard(url if isinstance(url, unicode) else unicode(url, 'utf-8', errors='ignore'))
        elif action == 'devReload' and DEV:
            reload_ = self._state.get('devReload')
            if reload_ is not None:
                reload_()
        elif entity is None:
            _logger.warning('no room, action %r ignored', args)
        elif action == 'takeSlot':
            # BaseRallyRoomView.assignSlotRequest(slot, -1)
            if entity.isCommander():
                return
            import account_helpers
            _sendRequest(AssignUnitCtx(account_helpers.getAccountDatabaseID(), int(args.get('slot')), 'prebattle/assign'))
        elif action == 'assign':
            dbID = int(args.get('dbID'))
            if dbID in entity.getPlayers():
                _sendRequest(AssignUnitCtx(dbID, int(args.get('slot')), 'prebattle/assign'))
        elif action == 'assignNext':
            self._assignNext(entity, int(args.get('dbID')))
        elif action == 'leaveSlot':
            # BaseRallyRoomView.leaveSlotRequest
            from UnitBase import UNIT_SLOT
            dbID = int(args.get('dbID'))
            if entity.getPlayerInfo(dbID=dbID).isInSlot:
                _sendRequest(AssignUnitCtx(dbID, UNIT_SLOT.REMOVE, 'prebattle/assign'))
        elif action == 'highlight':
            # BaseRallyRoomView.onSlotsHighlihgtingNeed (as_highlightSlotsS)
            self._highlight = list(entity.getPlayerInfo(int(args.get('dbID'))).getAvailableSlots(True))
            self._push()
        elif action == 'kick':
            if entity.getPlayerInfo().isCommander():
                _sendRequest(KickPlayerUnitCtx(int(args.get('dbID')), 'prebattle/kick'))
        elif action == 'ready':
            # BaseRallyRoomView.toggleReadyStateRequest
            entity.doAction()
        elif action == 'toggleOpen':
            isOpened = entity.getStrongholdSettings().getState().getPublic()
            _sendRequest(ChangeOpenedUnitCtx(not isOpened, 'prebattle/change_settings'))
        elif action == 'reserveOpen':
            self._reserveSlot = int(args.get('slot', -1))
            self._push()
        elif action == 'reserveSelect':
            # StrongholdBattleRoom._selectReserve
            from gui.prb_control.entities.stronghold.unit.ctx import SetReserveUnitCtx, UnsetReserveUnitCtx
            self._reserveSlot = -1
            reserveID = int(args.get('id'))
            if args.get('remove'):
                _sendRequest(UnsetReserveUnitCtx(reserveID, waitingID='prebattle/change_settings', isRemove=True))
            else:
                _sendRequest(SetReserveUnitCtx(reserveID, waitingID='prebattle/change_settings', isRemove=False))
            self._push()
        elif action == 'chatSend':
            text = (args.get('text') or u'').strip()
            controller = self._chat.controller() if self._chat is not None else None
            if text and controller is not None:
                controller.sendMessage(text.encode('utf-8') if isinstance(text, unicode) else text)
        elif action == 'contextMenuName':
            self._contextMenuByName(args.get('name') or u'')
        elif action == 'contextMenu':
            self._contextMenu(int(args.get('dbID')))
        elif action == 'chooseVehicle':
            self._chooseVehicle(entity, int(args.get('cd') or 0))
        elif action == 'role':
            give = bool(args.get('give'))
            _setEquipmentCommander(int(args.get('dbID')) if give else None, args.get('kind'))
        elif action == 'gridClick':
            # MinimapGrid.setClick: unit chat command in WG's 207 px grid
            controller = self._chat.controller() if self._chat is not None else None
            if controller is not None and self._packGrid(time.time())['clickEnabled']:
                controller.sendCommand(controller.proto.unitChat.createByMapPos(float(args.get('x')) * _GRID_SIZE, float(args.get('y')) * _GRID_SIZE))
        elif action == 'unfreeze':
            # StrongholdBattleRoom.onUnfrozenVehicleSlotClick -> WG's "back in service" dialog
            entity.onUnfreezeVehicleInSlot(int(args.get('slot')), parent=None)
        elif action == 'invite':
            self._whileWgWindow(self._openInvites)
        elif action == 'configure':
            self._whileWgWindow(self._openConfigure)
        elif action == 'eventReset':
            self._eventReset.reset(self.__onEventResetDone)
        elif action == 'searchCancel':
            # StrongholdBattleRoomWindow.autoSearchCancel
            if self._search is not None and entity.inPlayersMatchingMode():
                entity.exitFromPlayersMatchingMode()
            else:
                entity.exitFromQueue()
        elif action == 'maintenanceRefresh':
            # StrongholdBattleRoomWindow.refresh
            entity.requestMaintenanceUpdate()
        else:
            _logger.warning('unknown action %r', args)

    def _assignNext(self, entity, dbID):
        # commander clicked a volunteer: lowest free slot WG allows for him (same list as WG's
        # green slot highlighting)
        slots = self._parts.get('slots') or []
        free = lambda i: 0 <= i < len(slots) and isinstance(slots[i], dict) and not slots[i].get('player') \
            and not slots[i].get('isClosed') and not slots[i].get('isLocked')
        from gui.prb_control.entities.base.unit.ctx import AssignUnitCtx
        for slotIdx in sorted(entity.getPlayerInfo(dbID).getAvailableSlots(True)):
            if free(slotIdx):
                _sendRequest(AssignUnitCtx(dbID, slotIdx, 'prebattle/assign'))
                return
        _logger.info('no free slot for %s', dbID)

    def _playerVO(self, dbID):
        for slot in self._parts.get('slots') or ():
            player = slot.get('player') if isinstance(slot, dict) else None
            if player and player.get('dbID') == dbID:
                return player
        for item in self._parts.get('candidates') or ():
            if isinstance(item, dict) and item.get('dbID') == dbID:
                return item
        return None

    def _contextMenu(self, dbID):
        # WG's player menu (UNIT_USER), opened the way WG's Gameface platoon view does it
        vo = self._playerVO(dbID)
        if vo is None:
            _logger.warning('context menu: player %s not found', dbID)
            return
        if 'currentPlayer' in (vo.get('tags') or ()):
            return
        from gui.impl.backport import BackportContextMenuWindow
        from gui.impl.backport.backport_context_menu import createContextMenuData
        from gui.Scaleform.genConsts.CONTEXT_MENU_HANDLER_TYPE import CONTEXT_MENU_HANDLER_TYPE
        BackportContextMenuWindow(createContextMenuData(CONTEXT_MENU_HANDLER_TYPE.UNIT_USER, vo), self.getParentWindow()).load()

    def _contextMenuByName(self, name):
        # chat author: a player in the room gets the room menu (UNIT_USER), anyone else WG's normal
        # player menu (BASE_USER) with the dbID from the messenger's user storage
        if not name:
            return
        players = [slot.get('player') for slot in self._parts.get('slots') or () if isinstance(slot, dict)]
        players += [item for item in self._parts.get('candidates') or () if isinstance(item, dict)]
        for player in players:
            if player and _u(player.get('userName') or u'') == name and player.get('dbID'):
                self._contextMenu(player['dbID'])
                return
        from messenger.storage import MessengerStorageDescriptor, UsersStorage
        users = MessengerStorageDescriptor(UsersStorage).get()
        user = next((u for u in users.all() if _u(u.getName() or u'') == name), None)
        if user is None or user.isCurrentPlayer():
            return
        from gui.impl.backport import BackportContextMenuWindow
        from gui.impl.backport.backport_context_menu import createContextMenuData
        from gui.Scaleform.genConsts.CONTEXT_MENU_HANDLER_TYPE import CONTEXT_MENU_HANDLER_TYPE
        vo = {'dbID': user.getID(), 'userName': user.getName()}
        BackportContextMenuWindow(createContextMenuData(CONTEXT_MENU_HANDLER_TYPE.BASE_USER, vo), self.getParentWindow()).load()

    def _chooseVehicle(self, entity, currentCD=0):
        # EZ TANK PICKER if installed (its loader handles its dev mode), else WG's own selector
        # (BaseRallyRoomView._chooseVehicleRequest); both answer with CSVehicleSelectEvent
        levelsRange = entity.getRosterSettings().getLevelsRange()
        try:
            import sys
            pickerLoader = sys.modules.get('gui.mods.mod_advances_picker')
            if pickerLoader is not None:
                from advances_picker import impl as picker
                pickerLoader._reopen(levelsRange, picker._frozenCDs(_PopoverShim(entity)), currentCD)
                return
        except Exception:
            _logger.exception('opening EZ TANK PICKER failed, using WG selector')
        from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
        from gui.Scaleform.genConsts.CYBER_SPORT_ALIASES import CYBER_SPORT_ALIASES
        from gui.Scaleform.locale.CYBERSPORT import CYBERSPORT
        from gui.Scaleform.locale.FORTIFICATIONS import FORTIFICATIONS
        from gui.shared import events, g_eventBus
        from gui.shared.event_bus import EVENT_BUS_SCOPE
        from gui.shared.utils.requesters import REQ_CRITERIA
        from skeletons.gui.shared import IItemsCache
        playerInfo = entity.getPlayerInfo()
        vehicles = playerInfo.getSlotsToVehicles(True).get(playerInfo.slotIdx)
        if vehicles is not None:
            vehicles = dependency.instance(IItemsCache).items.getVehicles(REQ_CRITERIA.VEHICLE.SPECIFIC_BY_CD(vehicles))
        g_eventBus.handleEvent(events.LoadViewEvent(SFViewLoadParams(CYBER_SPORT_ALIASES.VEHICLE_SELECTOR_POPUP_PY), ctx={
            'isMultiSelect': False,
            'vehicles': vehicles,
            'titleText': CYBERSPORT.WINDOW_VEHICLESELECTOR_TITLE,
            'selectButton': CYBERSPORT.WINDOW_VEHICLESELECTOR_BUTTONS_SELECT,
            'cancelButton': CYBERSPORT.WINDOW_VEHICLESELECTOR_BUTTONS_CANCEL,
            'infoText': FORTIFICATIONS.SORTIE_VEHICLESELECTOR_DESCRIPTION,
            'compatibleOnlyLabel': CYBERSPORT.WINDOW_VEHICLESELECTOR_FILTERS_MATCHES,
            'selectedVehicles': self._selectedVehicles(entity),
            'section': 'cs_unit_view_vehicle',
            'levelsRange': levelsRange}), scope=EVENT_BUS_SCOPE.LOBBY)

    def _openInvites(self):
        # StrongholdBattleRoom.inviteFriendRequest
        from constants import PREBATTLE_TYPE, PREBATTLE_TYPE_NAMES
        from gui.Scaleform.framework.managers.loaders import SFViewLoadParams
        from gui.Scaleform.genConsts.FORTIFICATION_ALIASES import FORTIFICATION_ALIASES
        from gui.prb_control.settings import CTRL_ENTITY_TYPE
        from gui.shared import events, g_eventBus
        from gui.shared.event_bus import EVENT_BUS_SCOPE
        g_eventBus.handleEvent(events.LoadViewEvent(SFViewLoadParams(FORTIFICATION_ALIASES.STRONGHOLD_SEND_INVITES_WINDOW_PY), ctx={
            'prbName': PREBATTLE_TYPE_NAMES[PREBATTLE_TYPE.STRONGHOLD],
            'ctrlType': CTRL_ENTITY_TYPE.UNIT,
            'showClanOnly': False}), scope=EVENT_BUS_SCOPE.LOBBY)

    @adisp_process
    def _openConfigure(self):
        # StrongholdBattleRoom.openConfigureWindow (WG's modal browser with the change-mode page)
        from gui import GUI_SETTINGS
        from gui.clans.clan_helpers import getStrongholdChangeModeUrl
        from gui.Scaleform.daapi.view.lobby.strongholds.web_handlers import createStrongholdsWebHandlers
        from skeletons.gui.game_control import IBrowserController
        browserCtrl = dependency.instance(IBrowserController)
        windowSize = GUI_SETTINGS.lookup('StrongholdsPopupWebWindowSize') or {}
        browserSize = (windowSize.get('width', 800), windowSize.get('height', 600))
        self._configureBrowserId = yield browserCtrl.load(url=getStrongholdChangeModeUrl(), title=makeString(TOOLTIPS.CYBERSPORT_MODECHANGEFROZEN_HEADER),
                                                          browserSize=browserSize, isModal=True, showCreateWaiting=True,
                                                          handlers=createStrongholdsWebHandlers(), showActionBtn=False)
        browser = browserCtrl.getBrowser(self._configureBrowserId)
        if browser:
            browser.ignoreKeyEvents = True
        else:
            self._configureBrowserId = 0

    def _destroyConfigureWindow(self):
        # StrongholdBattleRoom.__destroyChangeModeWindow
        if not self._configureBrowserId:
            return
        from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
        from gui.shared.utils.functions import getViewName
        self._destroyFlashWindow(getViewName(VIEW_ALIAS.BROWSER_WINDOW_MODAL, self._configureBrowserId), alias=False)
        self._configureBrowserId = 0

    @staticmethod
    def _destroyFlashWindow(name, alias=True):
        from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
        from skeletons.gui.app_loader import IAppLoader
        app = dependency.instance(IAppLoader).getApp()
        if app is None or app.containerManager is None:
            return
        criteria = {POP_UP_CRITERIA.VIEW_ALIAS: name} if alias else {POP_UP_CRITERIA.UNIQUE_NAME: name}
        view = app.containerManager.getView(WindowLayer.WINDOW, criteria=criteria)
        if view is not None:
            view.destroy()

    def _whileWgWindow(self, opener):
        # WG's Flash windows (invites, configure) open on the same layer as the room: the panel is
        # hidden while one is up and comes back when it closes (window status events, no polling)
        try:
            baseline = _wgWindowCount(self._ownWindowID())
        except Exception:
            _logger.exception('counting windows failed')
            opener()
            return
        self._passive = {'baseline': baseline, 'seen': False}
        self._push(force=True)
        opener()

        def timeout():
            # the window never showed up (e.g. WG refused it): panel back
            if self._passive is not None and not self._passive['seen'] and not self._finalized:
                self._passive = None
                self._push(force=True)

        BigWorld.callback(3.0, timeout)

    # WG's own Flash tooltips (BackportTooltipWindow), used for the direction graphic
    def _showWgTip(self, kind, index):
        self._hideWgTip()
        from gui.impl.backport.backport_tooltip import BackportTooltipWindow, createTooltipData
        from gui.Scaleform.genConsts.TOOLTIPS_CONSTANTS import TOOLTIPS_CONSTANTS
        if kind == 'swords':
            data = createTooltipData(tooltip=makeString('#fortifications:strongholdtooltips/crossSwords'))
        else:
            data = createTooltipData(isSpecial=True, specialAlias=TOOLTIPS_CONSTANTS.DIRECT_MODULE, specialArgs=[index, 0])
        window = BackportTooltipWindow(data, self.getParentWindow())
        window.load()
        self._wgTip = window

    def _hideWgTip(self):
        window, self._wgTip = getattr(self, '_wgTip', None), None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                _logger.exception('hiding WG tooltip failed')


_WATCH_LAYERS = (WindowLayer.WINDOW, WindowLayer.TOP_WINDOW)


def _wgWindowCount(ignoreID):
    gui = dependency.instance(IGuiLoader)
    return len(gui.windowsManager.findWindows(lambda w: w.layer in _WATCH_LAYERS and w.uniqueID != ignoreID))


class EzRoomWindow(WindowImpl):
    # panel mode: plain window as big as the room panel, moved by Python
    __slots__ = ()

    def __init__(self, layoutID, state):
        super(EzRoomWindow, self).__init__(
            WindowFlags.WINDOW,
            content=EzRoomView(layoutID, state),
            parent=None,
            layer=WindowLayer.WINDOW,
            areaID=R.areas.default())


def _makeFullWindow(layoutID, state):
    # full mode: screen-sized window on WG's room layer (WINDOW_FULLSCREEN: the game sizes it, so
    # Gameface does not have to measure it; 0.8.0-0.8.3 sized it from JS and Gameface sometimes
    # reset it after "Size calculation timeout"); transparent, only the room panel takes mouse
    # input (Gameface hit test), so the garage stays usable around it
    from gui.impl.pub.lobby_window import LobbyWindow

    class EzRoomFullWindow(LobbyWindow):
        __slots__ = ()

    return EzRoomFullWindow(wndFlags=WindowFlags.WINDOW | WindowFlags.WINDOW_FULLSCREEN,
                            content=EzRoomView(layoutID, state), layer=WindowLayer.WINDOW)


def _layoutID():
    # R.mods.ez_room.views.EzRoomView, from res/gui/gen_resources
    node = getattr(R, 'mods', None)
    for key in _LAYOUT_PATH:
        node = node.dyn(key) if node is not None else None
    resID = node() if node is not None else -1
    if resID < 0:
        _logger.error('layout %s not registered', '.'.join(_LAYOUT_PATH))
        return None
    return resID


# --- called by the loader -------------------------------------------------------------------

def showRoom(state, toggle=False):
    # WG wants to show its room window: ours instead. True = handled (WG's window stays closed).
    if roomEntity() is None:
        return False
    window = state.get('window')
    if window is not None:
        if toggle and window.content is not None:
            window.content.minimize()
        return True
    destroyWgRoomWindow()
    if not state.get('opening'):
        state['opening'] = True
        BigWorld.callback(0.0, lambda: _openWindow(state))
    return True


def _openWindow(state):
    state['opening'] = False
    try:
        _loadWindow(state)
    except Exception:
        _logger.exception('opening the room window failed')
        window = state.get('window')
        if window is not None:
            # a partially opened window is destroyed before it is forgotten
            try:
                window.destroy()
            except Exception:
                _logger.exception('destroying the failed room window failed')
        state['window'] = None
        fallback = state.get('fallback')
        if fallback is not None:
            fallback('open failed')


def _loadWindow(state):
    if state.get('window') is not None or roomEntity() is None:
        return
    layoutID = _layoutID()
    if layoutID is None:
        raise RuntimeError('EZ ROOM layout missing')
    if loadSettings().get('windowMode') == 'panel':
        window = EzRoomWindow(layoutID, state)
    else:
        window = _makeFullWindow(layoutID, state)
    state['window'] = window
    window.load()
    _logger.info('room window opened')


# --- session counter ------------------------------------------------------------------------------
# Battles started from the current room: the start / end of the battle from the arena periods
# (BATTLE / AFTERBATTLE), the result from WG's battle results message (it arrives at the end of
# the battle, also when the player went back to the garage earlier; end = its arrival then).

def _isStrongholdBattle(bonusType):
    from constants import ARENA_BONUS_TYPE
    return bonusType in (ARENA_BONUS_TYPE.SORTIE_2, ARENA_BONUS_TYPE.FORT_BATTLE_2)


def _sessionPeriod(session, period, periodEndTime, periodLength):
    from constants import ARENA_PERIOD
    battle = session['pending'].get(session.get('current'))
    if battle is None:
        return
    if period == ARENA_PERIOD.BATTLE and battle['start'] is None:
        left = max(0.0, periodEndTime - BigWorld.serverTime()) if periodEndTime else periodLength
        battle['start'] = time.time() - max(0.0, periodLength - left)
    elif period == ARENA_PERIOD.AFTERBATTLE and battle['end'] is None:
        battle['end'] = time.time()


def onAvatarReady(state):
    session = state.get('session')
    player = BigWorld.player()
    arena = getattr(player, 'arena', None)
    if arena is not None and _isStrongholdBattle(arena.bonusType):
        # "ready after the battle": back in the room the player is set ready once (EzRoomView._autoReady)
        state['autoReady'] = {'since': None, 'tried': 0.0}
    if session is None or arena is None or not _isStrongholdBattle(arena.bonusType):
        return
    arenaUniqueID = player.arenaUniqueID
    if len(session['pending']) > 20:
        session['pending'].clear()
    session['pending'].setdefault(arenaUniqueID, {'start': None, 'end': None})
    session['current'] = arenaUniqueID
    _sessionPeriod(session, arena.period, arena.periodEndTime, arena.periodLength)


def onArenaPeriodChange(state, period, periodEndTime, periodLength, *args):
    session = state.get('session')
    if session is not None:
        _sessionPeriod(session, period, periodEndTime, periodLength)


def onServiceMessage(state, message):
    from chat_shared import SYS_MESSAGE_TYPE
    if message.type != SYS_MESSAGE_TYPE.battleResults.index():
        return
    session = state.get('session')
    data = message.data or {}
    battle = session['pending'].pop(data.get('arenaUniqueID'), None) if session is not None else None
    if battle is None:
        return
    duration = None
    if battle['start'] is not None:
        duration = (battle['end'] or time.time()) - battle['start']
        if not 0 < duration < 1800:
            duration = None
    session['battles'].append({'result': int(data.get('isWinner', 0) or 0), 'duration': duration})
    _logger.info('session: battle %s, result %s, %s s', len(session['battles']), data.get('isWinner'), duration)
    window = state.get('window')
    if window is not None and window.content is not None:
        window.content.mark()


def closeRoom(state):
    window = state.get('window')
    state['window'] = None
    state['reopen'] = False
    if window is not None:
        state['closing'] = True
        try:
            window.destroy()
        except Exception:
            _logger.exception('closing the room window failed')
        state['closing'] = False


def armReopen(state):
    # the game closed the room window (e.g. for the vehicle hub): open it again when a garage
    # window loads (window status event, no polling)
    state['reopen'] = True
    if state.get('reopenHook'):
        return
    wm = dependency.instance(IGuiLoader).windowsManager

    def onStatus(uniqueID, newStatus):
        from frameworks.wulf import WindowStatus
        if newStatus != WindowStatus.LOADED or not state.get('reopen'):
            return
        window = wm.getWindow(uniqueID)
        if window is None or window.layer != WindowLayer.SUB_VIEW or 'Hangar' not in type(window).__name__:
            return
        state['reopen'] = False
        if state.get('window') is None and roomEntity() is not None and not state.get('bypass'):
            _logger.info('garage is back: room window again')
            BigWorld.callback(0.3, lambda: showRoom(state))

    wm.onWindowStatusChanged += onStatus
    state['reopenHook'] = onStatus
