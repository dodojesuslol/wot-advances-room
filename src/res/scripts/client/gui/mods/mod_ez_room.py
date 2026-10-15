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
# opens (F5 inside the overlay reopens it). Optional "layer": a frameworks.wulf WindowLayer name.
import json
import logging
import os
import time
import types
import weakref

import BigWorld
from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room import StrongholdBattleRoom

_logger = logging.getLogger('EZ_ROOM')
_logger.setLevel(logging.INFO)
_DEV_FILE = os.path.join('mods', 'configs', 'ez_room', 'dev.json')
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
        self.title = None    # (isSortie, direction, resourceMultiplier) from _updateTitle
        self.window = None
        self.hidden = False
        self._pushPending = False

    @property
    def view(self):
        return self._view()

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
        if window is None:
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

    def open(self):
        if self.window is not None or self.view is None:
            return
        self.hidden = False
        try:
            self.window = _impl().openOverlay(self, _devConfig())
        except Exception:
            _logger.exception('opening room overlay failed, Flash room stays')
            self.window = None

    def close(self, hide=False):
        self.hidden = hide
        window, self.window = self.window, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                _logger.exception('closing room overlay failed')

    def reopen(self):
        self.close()
        BigWorld.callback(0.1, self.open)

    def onWindowGone(self, window):
        # called by the view's _finalize (window closed by the game or by us)
        if self.window is window:
            self.window = None


_bridge = None  # bridge of the room that is open right now


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
_origUpdateTitle = StrongholdBattleRoom._updateTitle


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


def _updateTitle(self, isSortie, direction, resourceMultiplier):
    _origUpdateTitle(self, isSortie, direction, resourceMultiplier)
    bridge = _bridge
    if bridge is not None and bridge.view is self:
        bridge.title = (isSortie, direction, resourceMultiplier)
        bridge.changed()


def _toggleOverlay():
    bridge = _bridge
    if bridge is None:
        return
    if bridge.window is None:
        bridge.open()
    else:
        bridge.close(hide=True)


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
StrongholdBattleRoom._populate = _populate
StrongholdBattleRoom._dispose = _dispose
StrongholdBattleRoom._updateTitle = _updateTitle
StrongholdBattleRoom._rebuildCandidatesDP = _wrapNotify(StrongholdBattleRoom._rebuildCandidatesDP)
StrongholdBattleRoom.initCandidatesDP = _wrapNotify(StrongholdBattleRoom.initCandidatesDP)
_registerModsList()
try:
    from ez_room.impl import __version__
except Exception:
    __version__ = '?'
_logger.info('mod_ez_room %s loaded%s', __version__, ' (dev mode)' if _devConfig() else '')
