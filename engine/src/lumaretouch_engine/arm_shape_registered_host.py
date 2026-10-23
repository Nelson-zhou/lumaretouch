# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual registered arm ports on the shared body/history/publication owner."""
from . import arm_shape_host as H, body_pose_render as R


class ArmRegisteredHostMixin:
    def _arm_journal(self):
        owner=self.__dict__.get('_arm_receipt_journal')
        if owner is None:
            from .arm_shape_receipts import ArmReceiptJournal
            owner=self._arm_receipt_journal=ArmReceiptJournal()
        return owner

    def _arm_prepare(self,candidate):
        prepared=self._body_prepare(candidate)
        return R.wrap_prepared(prepared,candidate,self._people_owner().snapshot(),self._people_source())

    def _arm_adapter(self):
        owner=self.__dict__.get('_arm_edit_owner')
        if owner is None:
            owner=H.ArmHostAdapter(H.HostPorts(self._people_binding,self._body_bank,lambda:self._people_owner().snapshot(),
                self._arm_prepare,self._body_publish,lambda key:self._arm_journal().get(key),
                lambda key,digest,result:self._arm_journal().put(key,digest,result),lambda key:self._arm_proposals().status(key),self._arm_cancel_proposals))
            self._arm_edit_owner=owner
        return owner

    def _arm_proposals(self):
        owner=self.__dict__.get('_arm_proposal_owner')
        if owner is None:
            from .arm_shape_job import ArmProposalJobs
            owner=H.ArmProposalHost(H.ProposalPorts(self._people_binding,self._body_bank,
                lambda:self._people_owner().snapshot(),lambda:self._doc_path),ArmProposalJobs())
            self._arm_proposal_owner=owner
        return owner

    def _arm_cancel_proposals(self):
        owner=self.__dict__.get('_arm_proposal_owner')
        if owner is not None:
            for key in list(owner.jobs.jobs):owner.cancel(key)

    def _arm_tick(self):
        owner=self.__dict__.get('_arm_proposal_owner')
        if owner is None:return
        from time import monotonic
        now=monotonic()
        if now<getattr(self,'_arm_next_tick',0):return
        self._arm_next_tick=now+.25
        for key,row in list(owner.jobs.jobs.items()):
            if row['result']['phase']=='pending':
                try:owner.status(key)
                except (ValueError,RuntimeError,OSError,IndexError):owner.cancel(key)

    def _arm_before_command(self,message):
        name=message.get('cmd');action=message.get('action')
        if name in ('hello','arm_shape'):return
        if name in ('session','project','history','batch','task','preset') and action in ('state','list'):return
        if name in ('shoulder_shape','leg_shape','waist_shape') and action in ('view','select','status'):return
        # Other work may change the source, association or memory admission.
        # End only this owned read-only model process, not another feature's edit.
        self._arm_cancel_proposals()

    def _arm_shutdown(self):
        owner=self.__dict__.get('_arm_proposal_owner')
        if owner is not None:owner.close()
        journal=self.__dict__.get('_arm_receipt_journal')
        if journal is not None:journal.close()

    def cmd_arm_shape(self,message):
        from .arm_shape_commands import ArmTransport
        from .server import emit
        owner=self.__dict__.get('_arm_transport')
        if owner is None:owner=self._arm_transport=ArmTransport()
        owner.handle(self,message,emit)
