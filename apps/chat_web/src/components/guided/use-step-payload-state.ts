"use client";

import { type Dispatch, type SetStateAction, useEffect, useState } from "react";

export function useStepPayloadState<T>(
  buildInitialState: () => T,
  deps: readonly unknown[],
): [T, Dispatch<SetStateAction<T>>] {
  const [state, setState] = useState<T>(buildInitialState);

  useEffect(() => {
    setState(buildInitialState());
  }, deps);

  return [state, setState];
}
