# -*- coding: utf-8 -*-
# EZ ROOM for ADV: loader.
# Since 0.8.0 WG's Flash battle room window (fortClanBattleRoom.swf) is not opened any more. WG
# opens it only through EventDispatcher.showStrongholdsWindow (from loadStrongholds, the channel
# carousel, invites, returning from battle, ...). That method is wrapped: in a room it shows our
# own Gameface room (ez_room.impl) instead, which talks to WG's stronghold unit entity directly.
# (0.8.0 used an event bus restriction: WG's event bus catches the "no" of a sync restriction
# itself, so WG's window opened anyway.)
#
# Fallback to WG's room, so nobody is left without a room:
#  - "WG-Raum" button in the room: WG's room once (minimize it, the next carousel click is EZ ROOM
#    again); the mods list entry always brings EZ ROOM back; settings.json "useWgRoom": true
#    switches EZ ROOM off for good
#  - automatically when EZ ROOM fails: an exception while opening, the web UI not reporting back,
#    or a client crash while the room was opening last time (opening.guard)
#  - any exception inside the wrapper opens WG's window as usual
#
# Dev mode: create <game>/mods/configs/ez_room/dev.json with
#   {"src": "X:/Projekte/wot-advances-room/src"}
# Then impl.py, app.js and style.css are read fresh from that folder every time the room opens
# (F5 inside the room reopens it).
import json
import logging
import os
import types

import BigWorld
from gui.shared import events, g_eventBus
from gui.shared.event_bus import EVENT_BUS_SCOPE, EventPriority
from gui.prb_control.events_dispatcher import EventDispatcher

_logger = logging.getLogger('EZ_ROOM')
_logger.setLevel(logging.INFO)
_DEV_FILE = os.path.join('mods', 'configs', 'ez_room', 'dev.json')
# crash guard: exists while the room is being opened; if the client dies in between, the next
# start finds it and uses WG's room for that session
_GUARD_FILE = os.path.join('mods', 'configs', 'ez_room', 'opening.guard')
_IMPL_PATH = 'res/scripts/client/ez_room/impl.py'
# Python 2 sets a module's globals to None when the module object dies, so every dev-loaded
# impl is kept alive here (open views and callbacks still use its functions).
_devModules = []

# shared with impl (survives dev reloads): the open room window and the fallback state
_state = {
    'window': None,
    'opening': False,
    'bypass': False,         # WG's room for the current room (until the player leaves it)
    'bypassOnce': False,     # bypass only until WG's window closes ("WG-Raum" button)
    'guardTripped': False,   # crash while opening last time: WG's room this session
    'carouselClick': False,  # the coming LoadViewEvent comes from a click on the carousel item
}
_implCache = [None]


def _devConfig():
    try:
        if os.path.isfile(_DEV_FILE):
            with open(_DEV_FILE, 'r') as f:
                config = json.load(f)
            if isinstance(config, dict) and config.get('src'):
                return config
    except Exception:
        _logger.exception('dev: reading %s failed', _DEV_FILE)
    return None


def _impl(fresh=False):
    config = _devConfig()
    if config is not None:
        if _implCache[0] is not None and not fresh:
            return _implCache[0]
        path = os.path.join(config['src'], _IMPL_PATH)
        try:
            with open(path, 'rb') as f:
                source = f.read()
            module = types.ModuleType('ez_room_dev_impl')
            module.__file__ = path
            exec compile(source, path, 'exec') in module.__dict__
            module.DEV = config
            _devModules.append(module)
            _implCache[0] = module
            _logger.info('dev: loaded impl from %s', path)
            return module
        except Exception:
            _logger.exception('dev: loading %s failed, using packaged impl', path)
    from ez_room import impl
    return impl


def _setGuard(on):
    try:
        if on:
            folder = os.path.dirname(_GUARD_FILE)
            if not os.path.isdir(folder):
                os.makedirs(folder)
            with open(_GUARD_FILE, 'w') as f:
                f.write('opening')
        elif os.path.isfile(_GUARD_FILE):
            os.remove(_GUARD_FILE)
    except Exception:
        _logger.exception('crash guard file failed')


def _enabled():
    if _state['bypass'] or _state['guardTripped']:
        return False
    try:
        return not _impl().loadSettings().get('useWgRoom')
    except Exception:
        _logger.exception('reading settings failed')
        return False


def _openWgRoom():
    # WG's own room window (straight to WG's method, past our wrapper)
    from gui.prb_control.events_dispatcher import g_eventDispatcher
    _origShowStrongholdsWindow(g_eventDispatcher)


def _fallback(reason):
    # EZ ROOM failed or the player wants WG's room: WG's room for this room
    _logger.warning("WG's room instead of EZ ROOM (%s)", reason)
    _state['bypass'] = True
    _state['bypassOnce'] = reason == 'user'
    try:
        impl = _impl()
        impl.closeRoom(_state)
        if impl.roomEntity() is not None:
            BigWorld.callback(0.0, _openWgRoom)
    except Exception:
        _logger.exception('fallback failed')
        BigWorld.callback(0.0, _openWgRoom)


def _devReload():
    _impl().closeRoom(_state)
    impl = _impl(fresh=True)
    BigWorld.callback(0.1, lambda: impl.showRoom(_state))


_state['fallback'] = _fallback
_state['devReload'] = _devReload


_origShowStrongholdsWindow = EventDispatcher.showStrongholdsWindow


def _showStrongholdsWindow(self):
    # WG wants to show its room window: in a room ours instead (web room list stays WG's)
    click, _state['carouselClick'] = _state['carouselClick'], False
    if _enabled():
        try:
            impl = _impl()
            if impl.roomEntity() is not None:
                if _state.get('window') is None and not _state.get('opening'):
                    _setGuard(True)
                    BigWorld.callback(5.0, lambda: _setGuard(False))
                if impl.showRoom(_state, toggle=click):
                    return
        except Exception:
            _logger.exception('EZ ROOM failed, WG room instead')
            _state['bypass'] = True
    return _origShowStrongholdsWindow(self)


def _onCarouselClick(event):
    # before WG's carousel handler: its click ends in showStrongholdsWindow (it only knows WG's
    # Flash window), there it toggles our room like WG's (open / minimize)
    try:
        if event.clientID == _clientID():
            _state['carouselClick'] = True
            BigWorld.callback(0.0, _clearClick)
    except Exception:
        _logger.exception('carousel click failed')


def _clearClick():
    _state['carouselClick'] = False


def _clientID():
    from constants import PREBATTLE_TYPE
    from messenger.ext import channel_num_gen
    return channel_num_gen.getClientID4Prebattle(PREBATTLE_TYPE.STRONGHOLD)


def _onRemoveChannel(event):
    # WG removes the room from the carousel when the player leaves it, enters the queue screen,
    # goes to battle, ...: the signal WG's carousel uses to close the room window
    try:
        if event.clientID != _clientID():
            return
        if (event.ctx or {}).get('closeWindow', True):
            _closeRoom()
        _state['bypass'] = False
        _state['bypassOnce'] = False
    except Exception:
        _logger.exception('remove channel handler failed')


def _closeRoom(*args):
    try:
        _impl().closeRoom(_state)
    except Exception:
        _logger.exception('closing the room failed')


def _toggle():
    # mods list entry: EZ ROOM back (also after "WG-Raum", a fallback or useWgRoom in settings.json)
    impl = _impl()
    settings = impl.loadSettings()
    if settings.get('useWgRoom'):
        settings['useWgRoom'] = False
        impl.saveSettings(settings)
    _state['bypass'] = False
    _state['bypassOnce'] = False
    _state['guardTripped'] = False
    _logger.info('EZ ROOM on (mods list)')
    if impl.roomEntity() is not None:
        impl.showRoom(_state)


def _onWgWindowDispose(orig):
    # WG's room closed or minimized after "WG-Raum": the next time it is EZ ROOM again
    def _dispose(self):
        try:
            if _state['bypassOnce']:
                _state['bypass'] = False
                _state['bypassOnce'] = False
                _logger.info("WG's room closed, EZ ROOM next time")
        except Exception:
            _logger.exception('WG window dispose hook failed')
        return orig(self)
    return _dispose


def _sessionCall(name):
    def call(*args):
        try:
            getattr(_impl(), name)(_state, *args)
        except Exception:
            _logger.exception('session counter %s failed', name)
    return call


def _registerModsList():
    try:
        from gui.modsListApi import g_modsListApi
        g_modsListApi.addModification(
            id='ez_advances_room',
            name='EZ ROOM for ADV',
            description='Vorstoß-Raum: EZ ROOM wieder anzeigen  ·  Advances room: show EZ ROOM again',
            icon='gui/maps/icons/ez_room/modslist.png',
            enabled=True,
            login=False,
            lobby=True,
            callback=_toggle)
    except Exception:
        _logger.exception('mods list entry failed')


def _install():
    EventDispatcher.showStrongholdsWindow = _showStrongholdsWindow
    from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room_window import StrongholdBattleRoomWindow
    StrongholdBattleRoomWindow._dispose = _onWgWindowDispose(StrongholdBattleRoomWindow._dispose)
    g_eventBus.addListener(events.ChannelCarouselEvent.OPEN_BUTTON_CLICK, _onCarouselClick, scope=EVENT_BUS_SCOPE.LOBBY, priority=EventPriority.HIGH)
    g_eventBus.addListener(events.PreBattleChannelEvent.REQUEST_TO_REMOVE_PRE_BATTLE_CHANNEL, _onRemoveChannel, scope=EVENT_BUS_SCOPE.LOBBY)
    from PlayerEvents import g_playerEvents
    g_playerEvents.onAvatarBecomePlayer += _closeRoom
    g_playerEvents.onAccountBecomeNonPlayer += _closeRoom
    g_playerEvents.onDisconnected += _closeRoom
    # session counter: battles started from the room (impl.onAvatarReady / onServiceMessage)
    g_playerEvents.onAvatarReady += _sessionCall('onAvatarReady')
    g_playerEvents.onArenaPeriodChange += _sessionCall('onArenaPeriodChange')
    from messenger.proto.events import g_messengerEvents
    g_messengerEvents.serviceChannel.onChatMessageReceived += lambda seqID, message: _sessionCall('onServiceMessage')(message)


if os.path.isfile(_GUARD_FILE):
    _state['guardTripped'] = True
    _setGuard(False)
    _logger.warning("last start crashed while opening EZ ROOM: WG's room this session (mods list entry turns EZ ROOM back on)")
try:
    _install()
except Exception:
    _logger.exception("EZ ROOM hooks failed, WG's room stays")
_registerModsList()
try:
    from ez_room.impl import __version__
except Exception:
    __version__ = '?'
_logger.info('mod_ez_room %s loaded%s', __version__, ' (dev mode)' if _devConfig() else '')
