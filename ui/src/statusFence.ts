/** Fence both initial status acceptance and continuations after asynchronous thumbnail reads. */
export function createStatusFence(){
  let issued=0,accepted=0,revision=-1;
  return {
    issue:()=>++issued,
    accept(ticket:number,docRevision:number){
      if(ticket<accepted||docRevision<revision)return false;
      accepted=ticket;revision=docRevision;return true;
    },
    current:(ticket:number,docRevision:number)=>ticket===accepted&&docRevision===revision,
  };
}
