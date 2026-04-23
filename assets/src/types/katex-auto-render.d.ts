declare module 'katex/dist/contrib/auto-render.mjs' {
  import { KatexOptions } from 'katex';
  export default function renderMathInElement(element: HTMLElement, options?: KatexOptions & {
    delimiters?: { left: string; right: string; display: boolean }[];
    ignoredTags?: string[];
    ignoredClasses?: string[];
    errorCallback?: (msg: string, err: Error) => void;
    preProcess?: (math: string) => string;
  }): void;
}
