# -*- coding: utf-8 -*-
# EZ ROOM for ADV: implementation. Loaded by gui/mods/mod_ez_room.py, either as the packaged
# module or, in dev mode, straight from the project source.
# The view gets the recorded Flash room state from the loader's RoomBridge, packs it into one
# JSON string for the web UI and runs actions through the room's own request methods.
import json
import logging
import os
import time

import BigWorld
from frameworks.wulf import ViewFlags, ViewModel, ViewSettings, WindowFlags, WindowLayer
from gui.impl.gen import R
from gui.impl.pub import ViewImpl
from gui.impl.pub.window_impl import WindowImpl
from gui.Scaleform.daapi.view.lobby.rally import vo_converters
from gui.Scaleform.locale.FORTIFICATIONS import FORTIFICATIONS
from gui.shared.utils.functions import getArenaGeometryName
from helpers import dependency, getClientLanguage
from helpers.i18n import makeString
from skeletons.gui.impl import IGuiLoader

__version__ = '0.7.4'
_logger = logging.getLogger('EZ_ROOM')
_logger.setLevel(logging.INFO)
_LAYOUT_PATH = ('ez_room', 'views', 'EzRoomView')
_UI_DIR = 'res/gui/gameface/mods/ez_room'
_SNAPSHOT_FILE = os.path.join('mods', 'configs', 'ez_room', 'last_room.json')  # dev only, for the preview
_SETTINGS_FILE = os.path.join('mods', 'configs', 'ez_room', 'settings.json')  # UI settings (team table sort)


def _loadSettings():
    try:
        if os.path.isfile(_SETTINGS_FILE):
            with open(_SETTINGS_FILE, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        _logger.exception('reading %s failed', _SETTINGS_FILE)
    return {}


def _saveSettings(settings):
    try:
        folder = os.path.dirname(_SETTINGS_FILE)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)
    except Exception:
        _logger.exception('writing %s failed', _SETTINGS_FILE)

# set by the loader in dev mode: contents of dev.json ({'src': 'X:/.../src', optional 'layer', 'offset'})
DEV = None
# size of the room content in WG's Flash window (FortClanBattleRoomUI, fortClanBattleRoom.swf)
_ROOM_W, _ROOM_H = 1013, 653
_CONTENT_OFFSET = (12, 35, _ROOM_W, _ROOM_H)
_TRACK_INTERVAL = 0.0  # every frame: the overlay follows WG's window while it is dragged


def _rect(window):
    # (x, y, w, h) of a wulf window, None if unknown
    if window is None:
        return None
    try:
        # plain position only: calculateGlobalPosition is a native call that may not be safe
        # on WG's Flash windows
        pos = window.position
        size = window.size
        return (float(pos[0]), float(pos[1]), float(size[0]), float(size[1]))
    except Exception:
        _logger.exception('reading window rect failed')
        return None


def _roomWindowView(bridge):
    getter = getattr(bridge, 'roomWindowView', None)
    if getter is not None:
        return getter()
    # loader < 0.2.2 (dev reload into an older client): read its module global
    import sys
    loader = sys.modules.get('gui.mods.mod_ez_room')
    ref = getattr(loader, '_roomWindowView', None) if loader is not None else None
    return ref() if ref is not None else None


def _roomRect(bridge):
    # geometry of WG's Flash room window, straight from Flash (the wulf window reports 0,0,0,0)
    view = _roomWindowView(bridge)
    if view is None:
        return None
    try:
        geom = view.as_getGeometryS()
        if geom and len(geom) >= 2:
            return tuple(float(v) for v in geom[:4])
    except Exception:
        _logger.exception('as_getGeometryS failed')
    return None


def _frame(roomRect, config):
    # overlay rect = room content of WG's window. as_getGeometryS gives the window's top-left
    # (incl. its shadow) and -1 as size; the content starts 12 px right / 35 px down (measured
    # in game, title bar above stays WG's) and is 1013 x 653 (fortClanBattleRoom.swf).
    x, y = roomRect[0], roomRect[1]
    dx, dy, w, h = (config or {}).get('offset') or _CONTENT_OFFSET
    return (int(round(x + dx)), int(round(y + dy)), int(w), int(h))


def _lang():
    try:
        return 'de' if (getClientLanguage() or '').lower().startswith('de') else 'en'
    except Exception:
        return 'en'


def _u(value):
    if isinstance(value, str):
        return value.decode('utf-8', 'replace')
    return value if value is not None else u''


def _img(path):
    # Flash style '../maps/icons/x.png' -> Gameface 'img://gui/maps/icons/x.png'
    path = _u(path)
    if path.startswith(u'..'):
        return u'img://gui' + path[2:]
    if path.startswith(u'gui/'):
        return u'img://' + path
    return path


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


def _title(bridge):
    if not bridge.title:
        return u''
    isSortie, direction, multiplier = bridge.title
    try:
        if isSortie:
            return _u(makeString(FORTIFICATIONS.STRONGHOLDTITLE_SORTIE))
        title = _u(makeString(FORTIFICATIONS.STRONGHOLDTITLE_STRONGHOLD)) % {'direction': _u(vo_converters.getDirection(direction))}
        if multiplier > 1:
            title += u' (x%s)' % multiplier
        return title
    except Exception:
        _logger.exception('title failed')
        return u''


def _mapIcon(mapID):
    if not mapID:
        return u''
    try:
        return u'img://gui/maps/icons/map/stats/%s.png' % getArenaGeometryName(mapID)
    except Exception:
        return u''


def _me(view):
    try:
        info = view.prbEntity.getPlayerInfo()
        return {'dbID': info.dbID, 'isCommander': info.isCommander(), 'isInSlot': info.isInSlot,
                'isReady': info.isReady, 'slotIdx': getattr(info, 'slotIdx', -1) if info.isInSlot else -1}
    except Exception:
        _logger.exception('player info failed')
        return {}


# --- room chat ----------------------------------------------------------------------
# The room window's ChannelComponent (Flash chat box) is bound to the unit channel controller.
# We read the controller's history, send through the component (same checks as Flash) and get
# notified of new lines through a hook on ChannelComponent.as_addMessageS.
_CHAT_LINES = 150


def _chatComponent(bridge):
    windowView = _roomWindowView(bridge)
    try:
        return getattr(windowView, 'chat', None) if windowView is not None else None
    except Exception:
        _logger.exception('chat component lookup failed')
        return None


def _packChat(bridge):
    component = _chatComponent(bridge)
    controller = component._controller() if component is not None else None
    if controller is None:
        return {'joined': False, 'lines': []}
    try:
        history = list(controller.getHistory() or ())
        return {'joined': bool(controller.isJoined()), 'lines': history[-_CHAT_LINES:]}
    except Exception:
        _logger.exception('chat history failed')
        return {'joined': False, 'lines': []}


def _installChatHook():
    # once per client session (survives dev reloads: the wrapper only uses the loader module)
    from messenger.gui.Scaleform.view.lobby.ChannelComponent import ChannelComponent
    if getattr(ChannelComponent, '_ezRoomChatHook', False):
        return
    orig = ChannelComponent.as_addMessageS

    def as_addMessageS(self, message):
        result = orig(self, message)
        try:
            import sys
            loader = sys.modules.get('gui.mods.mod_ez_room')
            bridge = loader.currentBridge() if loader is not None else None
            if bridge is not None and bridge.window is not None:
                windowView = bridge.roomWindowView() if hasattr(bridge, 'roomWindowView') else None
                if windowView is not None and getattr(windowView, 'chat', None) is self:
                    bridge.changed()
        except Exception:
            logging.getLogger('EZ_ROOM').exception('chat hook failed')
        return result

    ChannelComponent.as_addMessageS = as_addMessageS
    ChannelComponent._ezRoomChatHook = True


# --- enemy search stays WG's original -------------------------------------------------
# While WG's room window shows its auto search form (as_changeAutoSearchStateS ...
# as_hideAutoSearchS) the overlay is hidden so the original form is visible and usable; it comes
# back when the search ends.

def _searchActive(bridge):
    windowView = _roomWindowView(bridge)
    return bool(getattr(windowView, 'currentState', '')) if windowView is not None else False


def _installSearchHooks():
    # once per client session; the wrappers only use the loader module
    from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room_window import StrongholdBattleRoomWindow
    if StrongholdBattleRoomWindow.__dict__.get('_ezRoomSearchHooks'):
        return
    origShow = StrongholdBattleRoomWindow.as_changeAutoSearchStateS
    origHide = StrongholdBattleRoomWindow.as_hideAutoSearchS

    def bridgeOf(windowView):
        import sys
        loader = sys.modules.get('gui.mods.mod_ez_room')
        bridge = loader.currentBridge() if loader is not None else None
        if bridge is None or bridge.roomWindowView() is not windowView:
            return None
        return bridge

    def as_changeAutoSearchStateS(self, value):
        result = origShow(self, value)
        try:
            bridge = bridgeOf(self)
            if bridge is not None and bridge.window is not None:
                logging.getLogger('EZ_ROOM').info('enemy search started: overlay hidden, WG form visible')
                bridge.searchHid = True
                bridge.close(hide=True)
        except Exception:
            logging.getLogger('EZ_ROOM').exception('search start hook failed')
        return result

    def as_hideAutoSearchS(self):
        result = origHide(self)
        try:
            bridge = bridgeOf(self)
            if bridge is not None and getattr(bridge, 'searchHid', False):
                logging.getLogger('EZ_ROOM').info('enemy search ended: overlay back')
                bridge.searchHid = False
                BigWorld.callback(0.1, lambda: bridge.open(manual=True))
        except Exception:
            logging.getLogger('EZ_ROOM').exception('search end hook failed')
        return result

    StrongholdBattleRoomWindow.as_changeAutoSearchStateS = as_changeAutoSearchStateS
    StrongholdBattleRoomWindow.as_hideAutoSearchS = as_hideAutoSearchS
    StrongholdBattleRoomWindow._ezRoomSearchHooks = True


# --- WG's waiting animation ("loading data") -------------------------------------------
# The room window shows it (as_setWaitingS) while the stronghold data is not valid, e.g. after
# the commander changed the settings. The overlay shows its own cover with WG's text meanwhile.

def _installWaitingHook():
    # once per client session; state is kept on the window view (survives dev reloads)
    from gui.Scaleform.daapi.view.lobby.fortifications.stronghold_battle_room_window import StrongholdBattleRoomWindow
    if StrongholdBattleRoomWindow.__dict__.get('_ezRoomWaitingHook'):
        return
    orig = StrongholdBattleRoomWindow.as_setWaitingS

    def as_setWaitingS(self, visible, message):
        result = orig(self, visible, message)
        try:
            self._ezRoomWaiting = (bool(visible), message)
            import sys
            loader = sys.modules.get('gui.mods.mod_ez_room')
            bridge = loader.currentBridge() if loader is not None else None
            if bridge is not None and bridge.window is not None and bridge.roomWindowView() is self:
                bridge.changed()
        except Exception:
            logging.getLogger('EZ_ROOM').exception('waiting hook failed')
        return result

    StrongholdBattleRoomWindow.as_setWaitingS = as_setWaitingS
    StrongholdBattleRoomWindow._ezRoomWaitingHook = True


def _packWaiting(bridge):
    # WG's waiting text while the room waits for data, else None
    windowView = _roomWindowView(bridge)
    if windowView is None:
        return None
    state = getattr(windowView, '_ezRoomWaiting', None)
    if state is None:
        # hook came after the room opened (dev reload): same rule as WG's invalidateStrongholdWaiting
        try:
            view = bridge.view
            state = (view is not None and not view.prbEntity.isStrongholdSettingsValid(), '#waiting:prebattle/change_settings')
        except Exception:
            _logger.exception('waiting state failed')
            return None
    visible, message = state
    if not visible:
        return None
    try:
        text = _u(makeString(message)) if message else u''
    except Exception:
        text = u''
    return text if text and not text.startswith(u'#') else u'…'


# --- reserves ------------------------------------------------------------------------
# Same list as WG's FortReserveSelectPopover; selecting runs the room's _selectReserve.
def _packReserveOptions(view, slotIndex):
    from gui.Scaleform.daapi.view.lobby.rally import vo_converters as rally_vo
    entity = view.prbEntity
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


def _pack(bridge, frame=None, reserveSlot=-1):
    view = bridge.view
    calls = bridge.calls
    first = lambda name, default=None: calls[name][0] if name in calls and calls[name] else default
    now = time.time()
    room = first('as_setBattleRoomDataS', {}) or {}
    members = calls.get('as_setMembersS')
    slots = list(members[1]) if members and len(members) > 1 else list((first('as_updateRallyS', {}) or {}).get('slots') or [])
    # per-slot updates that came after the last full member list
    slots = [dict(s) if isinstance(s, dict) else s for s in slots]
    for idx, args in bridge.slotCalls.get('as_setMemberStatusS', {}).iteritems():
        if 0 <= idx < len(slots) and isinstance(slots[idx], dict):
            slots[idx]['playerStatus'] = args[0]
    for idx, args in bridge.slotCalls.get('as_setMemberOfflineS', {}).iteritems():
        if 0 <= idx < len(slots) and isinstance(slots[idx], dict) and slots[idx].get('player'):
            slots[idx]['player'] = dict(slots[idx]['player'], isOffline=args[0])
    for idx, args in bridge.slotCalls.get('as_setMemberVehicleS', {}).iteritems():
        if 0 <= idx < len(slots) and isinstance(slots[idx], dict) and len(args) > 1:
            slots[idx]['selectedVehicle'] = args[1]
    candidates = []
    try:
        dp = getattr(view, '_candidatesDP', None) if view is not None else None
        if dp is not None:
            candidates = list(dp.collection)
    except Exception:
        _logger.exception('candidates failed')
    timer = first('as_setTimerDeltaS')
    data = {
        'version': __version__,
        'frame': list(frame) if frame else None,
        'lang': _lang(),
        'dev': bool(DEV),
        'title': _title(bridge),
        'me': _me(view) if view is not None else {},
        'room': room,
        'mapIcon': _mapIcon(room.get('mapID')),
        'rally': first('as_updateRallyS', {}),
        'slots': slots,
        'candidates': candidates,
        'tableHeader': first('as_setTableHeaderS', []),
        'timer': timer,
        'timerAge': now - bridge.times.get('as_setTimerDeltaS', now),
        'readyStatus': calls.get('as_updateReadyStatusS'),
        'readyDirections': first('as_updateReadyDirectionsS'),
        'direction': calls.get('as_setDirectionS'),
        'reserves': first('as_setReservesDataS', []),
        'reservesEnabled': first('as_setReservesEnabledS', []),
        'opened': calls.get('as_setOpenedS'),
        'configure': first('as_setConfigureButtonStateS'),
        'actionButton': _actionButton(first('as_setActionButtonStateS')),
        'comment': first('as_setCommentS', u''),
        'vehiclesTitle': calls.get('as_setVehiclesTitleS'),
        'teamHeaderText': first('as_updateTeamHeaderTextS'),
        'filters': first('as_setFiltersDataS'),
        'highlight': first('as_highlightSlotsS'),
        'chat': _packChat(bridge),
        'waiting': _packWaiting(bridge),
        'reserveOptions': None,
        'settings': _loadSettings(),
    }
    if reserveSlot >= 0 and view is not None:
        try:
            data['reserveOptions'] = _packReserveOptions(view, reserveSlot)
        except Exception:
            _logger.exception('reserve options failed')
    if DEV:
        data['raw'] = {'calls': calls, 'slotCalls': bridge.slotCalls}
    return _clean(data)


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

    def __init__(self, layoutID, bridge, config):
        settings = ViewSettings(layoutID, flags=ViewFlags.VIEW, model=EzRoomModel())
        super(EzRoomView, self).__init__(settings)
        self._bridge = bridge
        self._config = config or {}
        self._snapshotPending = False
        self._frame = None      # (x, y, w, h) the overlay should cover
        self._roomRect = None   # last seen rect of WG's room window
        self._tracking = False
        self._loggedRect = False
        self._reserveSlot = -1  # reserve slot whose list is open

    @property
    def viewModel(self):
        return super(EzRoomView, self).getViewModel()

    def _onLoading(self, *args, **kwargs):
        super(EzRoomView, self)._onLoading(*args, **kwargs)
        if DEV:
            self.viewModel.setDev(_devUI())
        self.onRoomChanged()
        # move only after the window is loaded (like WG's OfferBannerWindow: load(), then move)
        self._tracking = True
        BigWorld.callback(0.2, self._trackNext)

    # follow WG's room window (moved by dragging its title bar) ---------------------

    def _track(self):
        try:
            roomRect = _roomRect(self._bridge)
            if roomRect is not None and roomRect != self._roomRect:
                self._roomRect = roomRect
                frame = _frame(roomRect, self._config)
                sizeChanged = self._frame is None or frame[2:] != self._frame[2:]
                self._frame = frame
                window = self.getParentWindow()
                if window is not None:
                    window.move(frame[0], frame[1])
                if not self._loggedRect:
                    self._loggedRect = True
                    _logger.info('room window rect %r -> overlay frame %r', roomRect, frame)
                    BigWorld.callback(1.0, lambda: _logger.info('overlay window after move: %r', _rect(self.getParentWindow())))
                if sizeChanged:
                    self.onRoomChanged()
        except Exception:
            _logger.exception('tracking room window failed')
        BigWorld.callback(_TRACK_INTERVAL, self._trackNext)

    def _trackNext(self):
        if self._tracking:
            self._track()

    def _getEvents(self):
        return ((self.viewModel.onAction, self.__onAction),)

    def _finalize(self):
        self._tracking = False
        try:
            bridge = self._bridge
            window = bridge.window
            if window is not None and window.content in (None, self):
                # destroyed by the game, not by us (bridge.close clears bridge.window first): WG's
                # fullscreen manager closes every other FULLSCREEN_WINDOW when one opens
                bridge.window = None
                _reopenAfterExternalClose(bridge, window.uniqueID)
        except Exception:
            _logger.exception('finalize failed')
        super(EzRoomView, self)._finalize()

    def onRoomChanged(self):
        try:
            data = _pack(self._bridge, self._frame, self._reserveSlot)
            self.viewModel.setData(json.dumps(data))
        except Exception:
            _logger.exception('packing room data failed')
            return
        if DEV and not self._snapshotPending:
            self._snapshotPending = True
            BigWorld.callback(2.0, self._writeSnapshot)

    def _writeSnapshot(self):
        # dev only: last room state as a file, used by the browser preview harness
        self._snapshotPending = False
        try:
            path = os.path.dirname(_SNAPSHOT_FILE)
            if not os.path.isdir(path):
                os.makedirs(path)
            with open(_SNAPSHOT_FILE, 'wb') as f:
                f.write(json.dumps(_pack(self._bridge, self._frame), indent=1, sort_keys=True).encode('utf-8'))
        except Exception:
            _logger.exception('writing snapshot failed')

    def __onAction(self, args=None):
        args = args or {}
        action = args.get('action')
        try:
            bridge = self._bridge
            if action == 'hide':
                bridge.close(hide=True)
            elif action == 'takeSlot':
                bridge.call('assignSlotRequest', int(args.get('slot')), -1)
            elif action == 'assign':
                bridge.call('assignSlotRequest', int(args.get('slot')), int(args.get('dbID')))
            elif action == 'leaveSlot':
                bridge.call('leaveSlotRequest', int(args.get('dbID')))
            elif action == 'highlight':
                # fills data.highlight with the slots this player may go to (as_highlightSlotsS)
                bridge.call('onSlotsHighlihgtingNeed', int(args.get('dbID')))
            elif action == 'kick':
                bridge.call('requestToKickUser', int(args.get('dbID')))
            elif action == 'ready':
                bridge.call('toggleReadyStateRequest')
            elif action == 'toggleOpen':
                bridge.call('toggleRoomStatus')
            elif action == 'reserveOpen':
                self._reserveSlot = int(args.get('slot', -1))
                self.onRoomChanged()
            elif action == 'reserveSelect':
                self._reserveSlot = -1
                view = bridge.view
                if view is not None:
                    view._selectReserve({'newId': int(args.get('id')), 'oldId': None, 'isRemove': bool(args.get('remove'))})
                self.onRoomChanged()
            elif action == 'sort':
                settings = _loadSettings()
                settings['sort'] = {'key': args.get('key') or u'', 'dir': int(args.get('dir') or 0)}
                _saveSettings(settings)
            elif action == 'chatSend':
                text = (args.get('text') or u'').strip()
                component = _chatComponent(bridge)
                if text and component is not None:
                    component.sendMessage(text.encode('utf-8') if isinstance(text, unicode) else text)
            elif action == 'contextMenu':
                self._contextMenu(int(args.get('dbID')))
            elif action == 'chooseVehicle':
                self._chooseVehicle(int(args.get('cd') or 0))
            elif action == 'invite':
                _whileWgWindow(bridge, lambda: bridge.call('inviteFriendRequest'))
            elif action == 'configure':
                _whileWgWindow(bridge, lambda: bridge.call('openConfigureWindow'))
            elif action == 'devReload' and DEV:
                self._bridge.reopen()
            elif action == 'log':
                _logger.info('ui: %s', args.get('msg'))
                if self._frame:
                    _logger.info('overlay window rect %r, frame %r', _rect(self.getParentWindow()), self._frame)
            else:
                _logger.warning('unknown action %r', args)
        except Exception:
            _logger.exception('action %r failed', args)

    def _contextMenu(self, dbID):
        # WG's player menu (UNIT_USER), opened the way WG's Gameface platoon view does it, with
        # the same player VO the Flash room would pass
        bridge = self._bridge
        view = bridge.view
        if view is None:
            return
        vo = None
        members = bridge.calls.get('as_setMembersS')
        for slot in (members[1] if members and len(members) > 1 else ()):
            player = slot.get('player') if isinstance(slot, dict) else None
            if player and player.get('dbID') == dbID:
                vo = player
                break
        if vo is None:
            dp = getattr(view, '_candidatesDP', None)
            for item in (dp.collection if dp is not None else ()):
                if isinstance(item, dict) and item.get('dbID') == dbID:
                    vo = item
                    break
        if vo is None:
            _logger.warning('context menu: player %s not found', dbID)
            return
        if 'currentPlayer' in (vo.get('tags') or ()):
            return
        from gui.impl.backport import BackportContextMenuWindow
        from gui.impl.backport.backport_context_menu import createContextMenuData
        from gui.Scaleform.genConsts.CONTEXT_MENU_HANDLER_TYPE import CONTEXT_MENU_HANDLER_TYPE
        window = BackportContextMenuWindow(createContextMenuData(CONTEXT_MENU_HANDLER_TYPE.UNIT_USER, vo), self.getParentWindow())
        window.load()

    def _chooseVehicle(self, currentCD=0):
        # EZ TANK PICKER if installed (its loader handles its dev mode), else WG's own selector
        bridge = self._bridge
        view = bridge.view
        if view is None:
            return
        try:
            import sys
            pickerLoader = sys.modules.get('gui.mods.mod_advances_picker')
            if pickerLoader is not None:
                from advances_picker import impl as picker
                entity = view.prbEntity
                levelsRange = entity.getRosterSettings().getLevelsRange()
                frozen = picker._frozenCDs(view)
                # the picker is a FULLSCREEN_WINDOW too: hide the overlay ourselves, back after it closes
                _whileWgWindow(bridge, lambda: pickerLoader._reopen(levelsRange, frozen, currentCD))
                return
        except Exception:
            _logger.exception('opening EZ TANK PICKER failed, using WG selector')
        _whileWgWindow(bridge, lambda: bridge.call('chooseVehicleRequest'))


# --- WG windows opened from the overlay ---------------------------------------------
# Flash windows (invites, configure, WG's vehicle selector) open on layer WINDOW, below the
# overlay: hide the overlay until the extra window is closed again.
_WATCH_LAYERS = (WindowLayer.WINDOW, WindowLayer.TOP_WINDOW, WindowLayer.FULLSCREEN_WINDOW)
_WATCH_TIMEOUT = 3.0  # s to wait for the WG window to appear


def _wgWindowCount(ignoreID):
    # our own overlay window is ignored (it may still be listed for a moment while destroyed)
    gui = dependency.instance(IGuiLoader)
    return len(gui.windowsManager.findWindows(lambda w: w.layer in _WATCH_LAYERS and w.uniqueID != ignoreID))


def _whileWgWindow(bridge, opener):
    own = bridge.window
    ownID = own.uniqueID if own is not None else -1
    try:
        baseline = _wgWindowCount(ownID)
    except Exception:
        _logger.exception('counting windows failed')
        opener()
        return
    bridge.close(hide=True)
    opener()
    state = {'seen': False, 'waited': 0.0}

    def poll():
        if bridge.view is None or bridge.window is not None:
            return  # room gone, or overlay reopened by hand
        try:
            count = _wgWindowCount(ownID)
        except Exception:
            _logger.exception('counting windows failed')
            count = baseline
        if count > baseline:
            state['seen'] = True
        state['waited'] += 0.25
        if (state['seen'] and count <= baseline) or (not state['seen'] and state['waited'] >= _WATCH_TIMEOUT):
            bridge.open(manual=True)
            return
        BigWorld.callback(0.25, poll)

    BigWorld.callback(0.25, poll)


def _reopenAfterExternalClose(bridge, ownID):
    # reopen once the window that pushed us out is gone (window count drops below its peak)
    try:
        state = {'max': _wgWindowCount(ownID)}
    except Exception:
        _logger.exception('counting windows failed')
        return
    _logger.info('overlay closed by the game, waiting to reopen it')

    def poll():
        if bridge.view is None or bridge.window is not None or bridge.hidden:
            return  # room gone, reopened by hand, or hidden on purpose
        try:
            count = _wgWindowCount(ownID)
        except Exception:
            _logger.exception('counting windows failed')
            return
        if count < state['max']:
            bridge.open(manual=True)
            return
        state['max'] = max(state['max'], count)
        BigWorld.callback(0.25, poll)

    BigWorld.callback(0.25, poll)


class EzRoomWindow(WindowImpl):
    # plain window (no decorator) laid exactly over the content of WG's room window
    # (same setup as WG's OfferBannerWindow: no parent, default area, moved after load)
    __slots__ = ()

    def __init__(self, layoutID, bridge, layer, config):
        super(EzRoomWindow, self).__init__(
            WindowFlags.WINDOW,
            content=EzRoomView(layoutID, bridge, config),
            parent=None,
            layer=layer,
            areaID=R.areas.default())


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


def openOverlay(bridge, devConfig=None):
    layoutID = _layoutID()
    if layoutID is None:
        return None
    # FULLSCREEN_WINDOW: above WG's Flash windows (WINDOW), same layer as the tank picker,
    # which therefore still opens on top
    layerName = (devConfig or {}).get('layer') or 'FULLSCREEN_WINDOW'
    layer = getattr(WindowLayer, layerName, WindowLayer.FULLSCREEN_WINDOW)
    if _roomWindowView(bridge) is None:
        _logger.warning('room window not found, overlay not opened')
        return None
    try:
        _installChatHook()
    except Exception:
        _logger.exception('installing chat hook failed')
    try:
        _installSearchHooks()
        _installWaitingHook()
    except Exception:
        _logger.exception('installing search hooks failed')
    if _searchActive(bridge):
        # WG's search form is up: it stays visible, the overlay comes back when it ends
        bridge.searchHid = True
        _logger.info('enemy search running, overlay stays hidden')
        return None
    window = EzRoomWindow(layoutID, bridge, layer, devConfig)
    window.load()
    _logger.info('overlay opened (layer %s, room window %r)', layerName, _roomRect(bridge))
    return window


# hooks as early as possible (the packaged impl is imported when the client starts), so a search
# that starts before the overlay opens is seen too
try:
    _installSearchHooks()
    _installWaitingHook()
except Exception:
    _logger.exception('installing search hooks failed')
