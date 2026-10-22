/** Extracted tool-panel composition keeps App routing readable and bounded. */
import {OpticsPanel} from '../optics/OpticsPanel';
import type {OpticsOwner} from '../optics/useOpticsWorkflow';
import type {OpticsReport} from '../optics/model';
import {ManualLiquifyPanel} from '../manualLiquify/ManualLiquifyPanel';
import {EffectRecoveryPanel} from '../effectRecovery/EffectRecoveryPanel';
import {StudioBackgroundPanel} from './StudioBackgroundPanel';
import type {ManualLiquifyOwner} from '../manualLiquify/useManualLiquifyWorkflow';
import type {EffectRecoveryOwner} from '../effectRecovery/useEffectRecoveryWorkflow';
import type {StudioOwner} from './useStudioBackgroundWorkflow';
import type {RecoveryReport} from '../effectRecovery/model';
import type {LiquifyReport} from '../manualLiquify/model';
import type {Report} from './model';
export function RetouchToolsPanels({manual,recovery,studio,manualReport,recoveryReport,studioReport,optics,opticsReport,busy}:{manual:ManualLiquifyOwner;recovery:EffectRecoveryOwner;studio:StudioOwner;optics:OpticsOwner;opticsReport?:OpticsReport;manualReport?:LiquifyReport;recoveryReport?:RecoveryReport;studioReport?:Report;busy:boolean}){
 return <><EffectRecoveryPanel owner={recovery} report={recoveryReport} disabled={optics.active||optics.pending||manual.active||manual.pending||studio.active||studio.pending||busy}/>
  <ManualLiquifyPanel owner={manual} report={manualReport} disabled={optics.active||optics.pending||recovery.active||recovery.pending||studio.active||studio.pending||busy}/>
  <StudioBackgroundPanel owner={studio} report={studioReport} disabled={optics.active||optics.pending||manual.active||manual.pending||recovery.active||recovery.pending||busy}/><OpticsPanel owner={optics} report={opticsReport} disabled={manual.active||manual.pending||recovery.active||recovery.pending||studio.active||studio.pending||busy}/></>;
}
