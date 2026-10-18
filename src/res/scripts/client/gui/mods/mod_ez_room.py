# -*- coding: utf-8 -*-
# EZ ROOM for ADV: loader.
# WG's Flash battle room (StrongholdBattleRoom) keeps running and keeps all its logic. This loader
# records every as_*S call the room sends to Flash (the full UI state) in a RoomBridge and shows
# our own Gameface view (ez_room.impl) on top, which renders that state and calls the room's
# own request methods for actions.
#
# Dev mode: create <game>/mods/configs/ez_room/dev.json with
#   {"src": "X:/Projekte/wot-advances-room/src"}
# Then impl.py, app.js and style.css are read fresh from that folder every time the overlay
# opens (F5 inside the overlay reopens it). Optional: "layer" (frameworks.wulf WindowLayer name),
# "offset" [dx, dy, w, h] = overlay rect relative to WG's room window position (default
# [12, 35, 1013, 653]: the room content, WG's title bar stays free).
import json
import logging
import os
import time
import types
import weakref

import BigWorld
from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room import StrongholdBattleRoom
from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room_window import StrongholdBattleRoomWindow

_logger = logging.getLogger('EZ_ROOM')
_logger.setLevel(logging.INFO)
_DEV_FILE = os.path.join('mods', 'configs', 'ez_room', 'dev.json')
# crash guard: exists while the overlay is being opened; if the client dies in between, the next
# start finds it and keeps the overlay off for that session (WG's Flash room stays usable)
_GUARD_FILE = os.path.join('mods', 'configs', 'ez_room', 'opening.guard')
_guardTripped = False
_IMPL_PATH = 'res/scripts/client/ez_room/impl.py'
# Python 2 sets a module's globals to None when the module object dies, so every dev-loaded
# impl is kept alive here (open views and callbacks still use its functions).
_devModules = []
# as_*S calls whose first argument is a slot index: kept per slot, reset by as_setMembersS
_PER_SLOT = ('as_setMemberStatusS', 'as_setMemberOfflineS', 'as_setMemberVehicleS')
_SKIP = ('as_getCandidatesDPS',)


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


def _impl():
    config = _devConfig()
    if config is not None:
        path = os.path.join(config['src'], _IMPL_PATH)
        try:
            with open(path, 'rb') as f:
                source = f.read()
            module = types.ModuleType('ez_room_dev_impl')
            module.__file__ = path
            exec compile(source, path, 'exec') in module.__dict__
            module.DEV = config
            _devModules.append(module)
            _logger.info('dev: loaded impl from %s', path)
            return module
        except Exception:
            _logger.exception('dev: loading %s failed, using packaged impl', path)
    from ez_room import impl
    return impl


class RoomBridge(object):
    """State of the open Flash room plus the link to our overlay window."""

    def __init__(self, view):
        self._view = weakref.ref(view)
        self.calls = {}      # as_*S name -> last args
        self.slotCalls = {}  # as_*S name -> {slotIdx: args}
        self.times = {}      # as_*S name -> time.time() of the last call (seconds)
        self.minimap = {'texture': u'', 'points': []}  # what WG's lobby minimap got (as_*S of MinimapLobby)
        self.grid = {'points': [], 'clickEnabled': False}  # commander markings (as_*S of MinimapGrid)
        self.window = None
        self.miniWindow = None  # small "EZ ROOM" button in WG's title bar while the original is shown
        self.hidden = False
        self._pushPending = False

    @property
    def view(self):
        return self._view()

    def roomWindowView(self):
        # WG's Flash room window view (StrongholdBattleRoomWindow); as_getGeometryS() = (x, y, w, h)
        return _roomWindowView() if _roomWindowView is not None else None

    def record(self, name, args):
        if name in _PER_SLOT and args:
            self.slotCalls.setdefault(name, {})[args[0]] = list(args[1:])
        else:
            self.calls[name] = list(args)
            if name == 'as_setMembersS':
                self.slotCalls = {}
        self.times[name] = time.time()
        self.changed()

    def changed(self):
        # many as_*S calls arrive in a burst: push once on the next tick
        if self._pushPending or self.window is None:
            return
        self._pushPending = True
        BigWorld.callback(0.0, self._push)

    def _push(self):
        self._pushPending = False
        window = self.window
        if window is None or window.content is None:
            return
        try:
            window.content.onRoomChanged()
        except Exception:
            _logger.exception('pushing room state failed')

    def call(self, name, *args):
        # runs one of the room's own Flash->Python handlers (assignSlotRequest, toggleReadyStateRequest, ...)
        view = self.view
        if view is None:
            _logger.warning('room is gone, %s ignored', name)
            return
        getattr(view, name)(*args)

    def open(self, manual=False):
        if self.window is not None or self.view is None:
            return
        if _guardTripped and not manual:
            _logger.warning('overlay stays off this session (last start crashed while opening it); open it with the EZ ROOM button')
            self.showMini()
            return
        self.closeMini()
        self.hidden = False
        _setGuard(True)
        try:
            self.window = _impl().openOverlay(self, _devConfig())
        except Exception:
            _logger.exception('opening room overlay failed, Flash room stays')
            self.window = None
        BigWorld.callback(3.0, lambda: _setGuard(False))

    def close(self, hide=False):
        self.hidden = hide
        window, self.window = self.window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                _logger.exception('closing room overlay failed')
        if not hide:
            self.closeMini()

    def showOriginal(self):
        # the user wants WG's room: overlay off, the small button brings it back
        self.close(hide=True)
        self.showMini()

    def showMini(self):
        if self.miniWindow is not None or self.view is None:
            return
        try:
            self.miniWindow = _impl().openMini(self, _devConfig())
        except Exception:
            _logger.exception('opening the EZ ROOM button failed')
            self.miniWindow = None

    def closeMini(self):
        window, self.miniWindow = self.miniWindow, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                _logger.exception('closing the EZ ROOM button failed')

    def reopen(self):
        self.close()
        BigWorld.callback(0.1, self.open)


_bridge = None  # bridge of the room that is open right now
_roomWindowView = None  # weakref to the StrongholdBattleRoomWindow (Flash window view)


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


def currentBridge():
    return _bridge


def _wrapCall(name, orig):
    def wrapper(self, *args):
        result = orig(self, *args)
        try:
            bridge = _bridge
            if bridge is not None and bridge.view is self:
                bridge.record(name, args)
        except Exception:
            _logger.exception('recording %s failed', name)
        return result
    wrapper.__name__ = name
    return wrapper


def _wrapNotify(orig):
    def wrapper(self, *args, **kwargs):
        result = orig(self, *args, **kwargs)
        bridge = _bridge
        if bridge is not None and bridge.view is self:
            bridge.changed()
        return result
    return wrapper


_origPopulate = StrongholdBattleRoom._populate
_origDispose = StrongholdBattleRoom._dispose


# WG's lobby minimap in the room (MinimapLobby.build): record exactly what Flash gets for the
# room's own minimap instance (bases, spawns, control points, points of interest)
def _roomMinimapBridge(minimap):
    bridge = _bridge
    view = bridge.view if bridge is not None else None
    if view is not None and getattr(view, '_StrongholdBattleRoom__minimap', None) is minimap:
        return bridge
    return None


def _wrapMinimap(name, orig):
    def wrapper(self, *args):
        result = orig(self, *args)
        try:
            bridge = _roomMinimapBridge(self)
            if bridge is not None:
                mm = bridge.minimap
                if name == 'as_clearS':
                    mm['points'] = []
                elif name == 'as_changeMapS':
                    mm['texture'] = args[0] if args else u''
                elif name == 'as_addPointS':
                    x, y, kind, color, number = args
                    mm['points'].append({'x': x, 'y': y, 'type': kind, 'color': color, 'id': number})
                elif name == 'as_addPoiS':
                    x, y, kind, number = args
                    mm['points'].append({'x': x, 'y': y, 'type': 'poi', 'poi': kind, 'id': number})
                bridge.changed()
        except Exception:
            _logger.exception('recording minimap %s failed', name)
        return result
    wrapper.__name__ = name
    return wrapper


# WG's MinimapGrid in the room (commander clicks a spot, everyone gets an ATTENTIONTOCELL unit chat
# command): record its points (WG grid px, 207 x 207) and whether clicking is allowed
def _wrapGrid(name, orig):
    def wrapper(self, *args):
        result = orig(self, *args)
        try:
            bridge = _bridge
            view = bridge.view if bridge is not None else None
            if view is not None and getattr(view, '_StrongholdBattleRoom__minimapGrid', None) is self:
                grid = bridge.grid
                if name == 'as_addPointS':
                    grid['points'] = [p for p in grid['points'] if time.time() - p['time'] < 10.0]
                    grid['points'].append({'x': args[0], 'y': args[1], 'time': time.time()})
                elif name == 'as_clearPointsS':
                    grid['points'] = []
                elif name == 'as_clickEnabledS':
                    grid['clickEnabled'] = bool(args[0]) if args else False
                bridge.changed()
        except Exception:
            _logger.exception('recording grid %s failed', name)
        return result
    wrapper.__name__ = name
    return wrapper


def _populate(self):
    global _bridge
    old = _bridge
    if old is not None:
        old.close()
    _bridge = RoomBridge(self)
    _origPopulate(self)
    BigWorld.callback(0.0, _bridge.open)


def _dispose(self):
    global _bridge
    bridge = _bridge
    if bridge is not None and bridge.view is self:
        _bridge = None
        bridge.close()
    _origDispose(self)


_origWindowPopulate = StrongholdBattleRoomWindow._populate
_origWindowDispose = StrongholdBattleRoomWindow._dispose


def _windowPopulate(self):
    global _roomWindowView
    _roomWindowView = weakref.ref(self)
    _origWindowPopulate(self)


def _windowDispose(self):
    global _roomWindowView
    if _roomWindowView is not None and _roomWindowView() is self:
        _roomWindowView = None
        if _bridge is not None:
            _bridge.close()
    _origWindowDispose(self)


def _toggleOverlay():
    bridge = _bridge
    if bridge is None:
        return
    if bridge.window is None:
        bridge.open(manual=True)
    else:
        bridge.showOriginal()


def _registerModsList():
    # "show / hide" entry in Poliroid's mods list button: brings the overlay back after
    # "show original"
    try:
        from gui.modsListApi import g_modsListApi
        g_modsListApi.addModification(
            id='ez_advances_room',
            name='EZ ROOM for ADV',
            description='Vorstoß-Raum: neue Oberfläche ein/aus  ·  Advances room: toggle the new UI',
            icon='gui/maps/icons/ez_room/modslist.png',
            enabled=True,
            login=False,
            lobby=True,
            callback=_toggleOverlay)
    except Exception:
        _logger.exception('mods list entry failed')


for _name in dir(StrongholdBattleRoom):
    if _name.startswith('as_') and _name.endswith('S') and _name not in _SKIP:
        setattr(StrongholdBattleRoom, _name, _wrapCall(_name, getattr(StrongholdBattleRoom, _name)))
try:
    from gui.Scaleform.daapi.view.lobby.MinimapLobby import MinimapLobby
    for _name in ('as_clearS', 'as_changeMapS', 'as_addPointS', 'as_addPoiS'):
        setattr(MinimapLobby, _name, _wrapMinimap(_name, getattr(MinimapLobby, _name)))
except Exception:
    _logger.exception('minimap hooks failed')
try:
    from gui.Scaleform.daapi.view.lobby.MinimapGrid import MinimapGrid
    for _name in ('as_addPointS', 'as_clearPointsS', 'as_clickEnabledS'):
        setattr(MinimapGrid, _name, _wrapGrid(_name, getattr(MinimapGrid, _name)))
except Exception:
    _logger.exception('grid hooks failed')
StrongholdBattleRoom._populate = _populate
StrongholdBattleRoomWindow._populate = _windowPopulate
StrongholdBattleRoomWindow._dispose = _windowDispose
StrongholdBattleRoom._dispose = _dispose
StrongholdBattleRoom._rebuildCandidatesDP = _wrapNotify(StrongholdBattleRoom._rebuildCandidatesDP)
StrongholdBattleRoom.initCandidatesDP = _wrapNotify(StrongholdBattleRoom.initCandidatesDP)
if os.path.isfile(_GUARD_FILE):
    _guardTripped = True
    _setGuard(False)
    _logger.warning('last start crashed while opening the overlay: overlay off for this session')
_registerModsList()
try:
    from ez_room.impl import __version__
except Exception:
    __version__ = '?'
_logger.info('mod_ez_room %s loaded%s', __version__, ' (dev mode)' if _devConfig() else '')
