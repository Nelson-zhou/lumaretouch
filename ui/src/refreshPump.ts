/** Coalesce panel status reads, but keep polling until acknowledged edits drain. */
export function createRefreshPump(
  read: () => Promise<boolean>,
  schedule: (run: () => void) => number,
  cancel: (id: number) => void,
) {
  let timer:number|null=null, running=false, dirty=false, disposed=false;
  const plan=()=>{
    if(disposed || running || timer!==null) return;
    timer=schedule(()=>{
      timer=null; running=true; dirty=false;
      void (async()=>{
        let busy=false;
        try {busy=await read();} catch { /* Caller surfaces status/engine errors. */ }
        finally {running=false;if(!disposed && (busy || dirty)) plan();}
      })();
    });
  };
  return {
    trigger(){if(!disposed){dirty=true;plan();}},
    dispose(){disposed=true;if(timer!==null)cancel(timer);timer=null;},
  };
}
