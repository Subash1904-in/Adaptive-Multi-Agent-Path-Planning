import "@testing-library/jest-dom/vitest";

// Mock ResizeObserver for jsdom
class MockResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

window.ResizeObserver = MockResizeObserver;

// Mock HTMLCanvasElement getContext for Three.js in jsdom
if (typeof HTMLCanvasElement !== "undefined") {
  HTMLCanvasElement.prototype.getContext = function (
    this: HTMLCanvasElement,
    contextType: string
  ) {

    if (contextType === "webgl" || contextType === "webgl2") {
      return {
        getExtension: () => null,
        getParameter: () => 0,
        createTexture: () => ({}),
        bindTexture: () => {},
        texParameteri: () => {},
        createProgram: () => ({}),
        createShader: () => ({}),
        shaderSource: () => {},
        compileShader: () => {},
        getShaderParameter: () => true,
        attachShader: () => {},
        linkProgram: () => {},
        getProgramParameter: () => true,
        useProgram: () => {},
        createBuffer: () => ({}),
        bindBuffer: () => {},
        bufferData: () => {},
        enableVertexAttribArray: () => {},
        vertexAttribPointer: () => {},
        drawArrays: () => {},
        drawElements: () => {},
        enable: () => {},
        disable: () => {},
        blendFunc: () => {},
        viewport: () => {},
        clearColor: () => {},
        clear: () => {},
        canvas: this,
      } as unknown as RenderingContext;
    }
    return null;
  } as typeof HTMLCanvasElement.prototype.getContext;
}
