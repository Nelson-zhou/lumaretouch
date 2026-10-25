// SPDX-License-Identifier: GPL-3.0-or-later
import {startEngine} from '../native';

/** Existing engine-start behavior extracted without changing lifecycle ownership. */
export function createStartEngineAction(options: {
  python: string; source: string; busy: (value: boolean) => void;
  pid: (value: number) => void; error: (value: string) => void;
}) {
  return async () => {
    options.busy(true);
    try {
      const result = await startEngine(options.python, options.source);
      options.pid(result.pid);
    } catch (error) {
      options.error(String(error));
    } finally {
      options.busy(false);
    }
  };
}
