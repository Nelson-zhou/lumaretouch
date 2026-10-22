/** Extracted tool-panel composition keeps App routing readable and bounded. */
import {ManualLiquifyPanel} from '../manualLiquify/ManualLiquifyPanel';
import {EffectRecoveryPanel} from '../effectRecovery/EffectRecoveryPanel';
import {StudioBackgroundPanel} from './StudioBackgroundPanel';
import type {ManualLiquifyOwner} from '../manualLiquify/useManualLiquifyWorkflow';
import type {EffectRecoveryOwner} from '../effectRecovery/useEffectRecoveryWorkflow';
import type {StudioOwner} from './useStudioBackgroundWorkflow';
import type {RecoveryReport} from '../effectRecovery/model';
import type {LiquifyReport} from '../manualLiquify/model';
import type {Report} from './model';
export function RetouchToolsPanels({manual,recovery,studio,manualReport,recoveryReport,studioReport,busy}:{manual:ManualLiquifyOwner;recovery:EffectRecoveryOwner;studio:StudioOwner;manualReport?:LiquifyReport;recoveryReport?:RecoveryReport;studioReport?:Report;busy:boolean}){
 return <><EffectRecoveryPanel owner={recovery} report={recoveryReport} disabled={manual.active||manual.pending||studio.active||studio.pending||busy}/>
  <ManualLiquifyPanel owner={manual} report={manualReport} disabled={recovery.active||recovery.pending||studio.active||studio.pending||busy}/>
  <StudioBackgroundPanel owner={studio} report={studioReport} disabled={manual.active||manual.pending||recovery.active||recovery.pending||busy}/></>;
}
