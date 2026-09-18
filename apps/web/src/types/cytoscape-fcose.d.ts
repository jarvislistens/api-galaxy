/**
 * `cytoscape-fcose` ships no type declarations.
 *
 * It is a Cytoscape layout extension, so the only shape that matters at the call site is
 * "something `cytoscape.use()` accepts". Declaring it as `Ext` keeps the registration
 * typed without pretending we know the layout's full option surface.
 */
declare module "cytoscape-fcose" {
  import type { Ext } from "cytoscape";

  const fcose: Ext;
  export default fcose;
}
