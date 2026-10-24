# SPDX-License-Identifier: GPL-3.0-or-later
"""One exact mixed-portrait review owner per preset, never generic transfer consent."""
from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class Family:
    name: str
    operation: str

    @property
    def ack(self): return self.name + '_preset_ack'

    @property
    def wire(self): return self.name + '_preset'

    @property
    def review(self): return import_module('.' + self.name + '_preset_review', __package__)

    @property
    def store(self): return import_module('.' + self.name + '_preset_store', __package__)

    def port(self, ports, prefix): return getattr(ports, prefix + self.name, None)

    def require_ports(self, ports):
        if (getattr(ports, self.name + '_replay', None) is None
                or getattr(ports, 'verify_' + self.name + '_applied', None) is None):
            raise ValueError('Exact portrait preset graph replay and post-render verification are unavailable')


def select(modules, *, eye_review=False, state=None):
    from .collarbone_scope import OP as COLLARBONE
    from .eye_bag_preserve_scope import OP as EYE_BAG
    from .eye_bag_preserve_scope import check_params, S
    eye_active=(type(modules) is dict and EYE_BAG in modules and S.active(check_params(modules[EYE_BAG])['recipe']))
    found = ([Family('collarbone',COLLARBONE)] if COLLARBONE in modules else [])
    if EYE_BAG in modules and (eye_review or eye_active):found.append(Family('eye_bag',EYE_BAG))
    from .face_decoration_scope import OP as DECORATION
    if decoration_required(modules,state):found.append(Family('face_decoration',DECORATION))
    if len(found) > 1:
        raise ValueError('Selected or retained portrait effects require distinct complete review owners; apply separately')
    return found[0] if found else None


def prune(reviews):
    from .collarbone_preset_store import prune as collarbone
    from .eye_bag_preset_store import prune as eye_bag
    from .face_decoration_preset_store import prune as decoration
    collarbone(reviews); eye_bag(reviews); decoration(reviews)


def decoration_required(modules, state=None):
    from .face_decoration_scope import OP, FIELD, S
    return (OP in modules or type(state) is dict and (
        state.get('_face_decoration_preset_retained_active') is True or S.active(S.check(state.get(FIELD)))))
