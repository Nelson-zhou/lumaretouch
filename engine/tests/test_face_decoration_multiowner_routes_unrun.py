# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored route-boundary fixtures, never executed during source development."""
import unittest


class DecorationMultiownerRouteContracts(unittest.TestCase):
    def test_cohort_image_is_an_exact_read_not_a_write(self):
        from lumaretouch_engine.creative_transfer_host import require_route
        packet={'cmd':'batch','action':'face_decoration_cohort_visual','request_id':'review',
                'preflight_token':'a'*32,'document_id':'b'*32,'revision':'1',
                'side':'after','sha256':'c'*64}
        require_route('batch',packet)
        with self.assertRaises(ValueError):
            require_route('batch',{**packet,'face_decoration_cohort_ack':[]})
        with self.assertRaises(ValueError):
            require_route('batch',{**packet,'side':'support'})

    def test_cohort_commit_transport_cannot_borrow_ordinary_ack(self):
        from lumaretouch_engine.creative_transfer_host import require_route
        # This only admits the envelope to its exact frozen controller. Empty
        # fake ACKs below do not authorize any mutation or validate a plan.
        packet={'cmd':'batch','action':'commit','request_id':'commit',
                'preflight_token':'a'*32,'module_scope':[],
                'face_decoration_cohort_ack':[]}
        require_route('batch',packet)
        require_route('batch',{**packet,'portrait_cohort_ack':[],
                              'eye_bag_cohort_ack':[],'collarbone_review_ack':[]})
        for key in ('face_decoration_review_ack','face_decoration_preset_ack',
                    'face_style_review_ack','recipe','support'):
            with self.assertRaises(ValueError):
                require_route('batch',{**packet,key:[]})
        incomplete=dict(packet);incomplete.pop('module_scope')
        with self.assertRaises(ValueError):require_route('batch',incomplete)


if __name__=='__main__':unittest.main()
