declare module "three-spritetext" {
  export default class SpriteText {
    constructor(text: string);
    material: { depthWrite: boolean; depthTest: boolean };
    textHeight: number;
    color: string;
    position: { x: number; y: number; z: number; set: (x: number, y: number, z: number) => void };
    renderOrder: number;
  }
}
