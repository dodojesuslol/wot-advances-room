# Mock room state in the shape of ez_room.impl._pack (used when no real snapshot exists).
# usage: python3 -I mock.py out.json [de|en]
import json, sys
lang = sys.argv[2] if len(sys.argv) > 2 else 'de'
V = [('germany', 'G56_E-100', 'E 100', 'heavyTank'), ('germany', 'G89_Leopard1', 'Leopard 1', 'mediumTank'),
     ('sweden', 'S16_Kranvagn', 'Kranvagn', 'heavyTank'), ('ussr', 'R45_IS-7', 'IS-7', 'heavyTank'),
     ('usa', 'A69_T110E5', 'T110E5', 'heavyTank'), ('ussr', 'R148_Object_430_U', 'Obj. 430U', 'mediumTank'),
     ('uk', 'GB91_Super_Conqueror', 'Super Conqueror', 'heavyTank'), ('france', 'F18_Bat_Chatillon25t', 'B-C 25 t', 'mediumTank')]
names = ['dodojesuslol', 'Panzerfaust_88', 'xXSniperXx', 'TigerKing', 'ArtyHater', 'Schnitzel_Tank', 'Blitzkrieg_77',
         'IronWolf', 'HE_Spammer', 'Pz_Commander', 'Kranvagn_Fan']
slots = []
for i in range(15):
    p = None
    veh = None
    if i < len(names):
        p = {'dbID': 100 + i, 'userName': names[i], 'fullName': names[i], 'colors': [13347959, 8483688],
             'isCommander': i == 0, 'isOffline': i == 7, 'readyState': i % 3 != 2, 'rating': '%d' % (5000 + 97 * i)}
        if i != 4:
            n, t, s, ty = V[i % len(V)]
            veh = {'intCD': i, 'level': 10, 'shortUserName': s, 'userName': s, 'type': ty,
                   'smallIconPath': '../maps/icons/vehicle/small/%s-%s.png' % (n, t), 'isReadyToFight': i != 6,
                   'enabled': True, 'state': u'Zu reparieren' if i == 6 else ''}
    slots.append({'player': p, 'selectedVehicle': veh, 'playerStatus': 2 if p and p['readyState'] else 0,
                  'rating': p['rating'] if p else '', 'isLegionaries': i == 9, 'isClosed': False, 'isLocked': False,
                  'slotLabel': '' if p else '<font color="#8c8c7c">Freier Platz</font>', 'canBeTaken': not p})
data = {'version': '0.1.0', 'lang': lang, 'dev': True, 'title': u'Vorstoß', 'me': {'dbID': 100, 'isCommander': True},
        'room': {'mapID': 5, 'mapName': 'Prokhorovka', 'headerDescr': '<font color="#8c8c7c">Stufe X · 15 Spieler</font>',
                 'mineClanName': '[CLAN]', 'enemyClanName': '[ENEMY]', 'waitForBattleDescr': ''},
        'mapIcon': 'img://gui/maps/icons/map/stats/05_prohorovka.png',
        'slots': slots,
        'candidates': [{'dbID': 900 + i, 'userName': n, 'rating': '6 812', 'colors': [13347959]} for i, n in enumerate(['Reservist_1', 'Late_Joiner', 'Tank_Enjoyer'])],
        'tableHeader': [{'label': u'Team: 11/15 (<img src="x"/> 1 / 3)'}],
        'timer': {'deltaTime': 299}, 'timerAge': 0, 'readyStatus': [True, False],
        'opened': ['Raum verbergen', u'Raum ist sichtbar', ''], 'comment': u'Nur Stufe X, bitte Sprachchat',
        'raw': {'calls': {'as_setTimerDeltaS': [{'deltaTime': 299}]}, 'slotCalls': {}}}
json.dump(data, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
