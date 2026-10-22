import {SkyReplacementPanel} from '../skyReplacement/SkyReplacementPanel';
import type {SkyReplacementOwner} from '../skyReplacement/useSkyReplacementWorkflow';
import type {SkyReport} from '../skyReplacement/model';
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
export function RetouchToolsPanels({manual,recovery,studio,manualReport,recoveryReport,studioReport,optics,opticsReport,sky,skyReport,busy}:{manual:ManualLiquifyOwner;recovery:EffectRecoveryOwner;studio:StudioOwner;optics:OpticsOwner;opticsReport?:OpticsReport;manualReport?:LiquifyReport;recoveryReport?:RecoveryReport;studioReport?:Report;busy:boolean;sky:SkyReplacementOwner;skyReport?:SkyReport}){
 return <><EffectRecoveryPanel owner={recovery} report={recoveryReport} disabled={sky.active||sky.pending||optics.active||optics.pending||manual.active||manual.pending||studio.active||studio.pending||busy}/>
  <ManualLiquifyPanel owner={manual} report={manualReport} disabled={sky.active||sky.pending||optics.active||optics.pending||recovery.active||recovery.pending||studio.active||studio.pending||busy}/>
  <StudioBackgroundPanel owner={studio} report={studioReport} disabled={sky.active||sky.pending||optics.active||optics.pending||manual.active||manual.pending||recovery.active||recovery.pending||busy}/><OpticsPanel owner={optics} report={opticsReport} disabled={sky.active||sky.pending||manual.active||manual.pending||recovery.active||recovery.pending||studio.active||studio.pending||busy}/><SkyReplacementPanel owner={sky} report={skyReport} disabled={optics.active||optics.pending||manual.active||manual.pending||recovery.active||recovery.pending||studio.active||studio.pending||busy}/></>;
}
