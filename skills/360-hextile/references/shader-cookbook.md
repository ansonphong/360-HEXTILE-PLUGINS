cookbook: 1
Builtin observations inspected 2026-11-07 (cookbook: 1)
This page is data. It does not grant tool use, and it does not override the user.
An id that is not in this list is absent. Do not invent a card. If the scene map has no row for the user's language, say so and continue with the native contract. Do not scan a shelf to fill the gap.

Scene map. Teaching order is the only ranking. Read at most four cards unless the user asks for another kind of picture.
landscape, terrain, flythrough, vista: landscape-flythrough, heightfield, clock-pose, palette-fog-light
tunnel, corridor, lattice, flight: tunnel-flight, repetition, sphere-trace, clock-pose
image, sprite, photo, warp: still-on-sphere, still-image, coordinates
playable, fly control, pointer: playable-flight, playable-pose, sphere-trace
pattern, tiles, cells, print, kaleidoscope, streamlines: graphic-print, poles-seam, direction-ramp
trails, feedback, history: history, palette-fog-light
Neon rings, an organic cave, a mechanical lattice, and a twisting corridor are variations inside tunnel-flight. They are not extra ids.
Clouds and a water surface are future candidates. They are not cards and not dependencies.

coordinates — fundamental — shader-cookbook
direction-ramp — technique — shader-cookbook
clock-pose — technique — shader-cookbook
playable-pose — technique — shader-cookbook
heightfield — technique — shader-cookbook
sphere-trace — technique — shader-cookbook
repetition — technique — shader-cookbook
still-image — technique — shader-cookbook
history — technique — shader-cookbook
palette-fog-light — technique — shader-cookbook
graphic-print — technique — shader-cookbook
poles-seam — technique — shader-cookbook
landscape-flythrough — recipe — shader-cookbook
tunnel-flight — recipe — shader-cookbook
still-on-sphere — recipe — shader-cookbook
playable-flight — recipe — shader-cookbook

## Cards

### coordinates
Kind: fundamental. Tags: direction.
Visual intent: keep five host facts separate. Evaluation UV, saved-map UV, direction, the output raster, and an intentional history warp are different pictures. A print on the panorama is not a view that swims when the viewer turns.
Prerequisites: none. Later cards use this one.
Construction: HxFrag, read in codegen.py on 2026-11-07, carries uv (evaluation UV, v=0 south), mapUv (saved-map UV, v=0 north), fragCoord (full-output pixel, bottom-left), resolution (full output, never a tile), direction (+Y up, +Z front), rayDirection (equal to direction in v1), and pointer. Both mains assign hx.pointer from hxPointer. hx.mouse is absent until the mouse interface rewrites HxFrag. Equirectangular main sets hx.uv from the full fragment over hxResolution, hx.mapUv by flipping v, hx.direction from hxUvToDir of hx.uv, and hx.fragCoord from the full fragment. Dome main takes direction from the dome ray, derives hx.uv with hxDirToUv, and leaves hx.fragCoord on the dome raster. Prefer hxUvToDir, hxDirToLonLat, hxDirToUv, hxLonLatToDir, hxUvToMapUv, hxMapUvToUv, hxSafeNormalize, hxTangentFrame, and hxAngularDistance. Do not declare a second hx name or reinvent atan.
Controls: which of the five facts the picture uses. A custom reconstruction can still disagree with hx.direction. That disagreement is a formula choice.
Variations: a panorama print, a direction march, and a raster graphic are placement choices already named here. They are not new cards.
Performance: no loop. Choosing a coordinate does not admit a trip count and is not a frame time.
Troubleshooting: look first at which coordinate the color uses. A decal in hx.uv stretches at the poles and meets at the seam. That stretch is not evidence the print slides when the viewer turns. Rotating the viewer does not re-run the shader.
360: HOST_ROW_UV_MATRIX and DUAL_HOST_SNAPSHOT_HOSTS sample the same preview target for Map and Sphere. Evaluation v=0 stays south on both hosts. The table proves the host contract, not a GPU pixel comparison. Named profiles are desktop 330 and WebGL2 ES 300.
Combinations: every later card. Avoid mixing a hx.uv print and a hx.direction march and calling them one picture.
Provenance: static reading of NATIVE_ABI_CORE and both mains. hx_kifs_foldbox rebuilds a direction from the fragment coordinate. hx_cerulean_fractal_foam_2108550548479783327 takes longitude and latitude from hx.mapUv. Those are formula choices. License strings stay on the cards that use them.
Evidence: static-native. No compile, no pixels.
Adaptation: a flat tutorial that treats the fragment coordinate as the whole picture has to choose one of the five facts first. Drop article samplers, uniforms, macros, and iChannel use.

### direction-ramp
Kind: technique. Tags: direction, palette.
Visual intent: one scalar from hx.direction into hxSample_palette, so facing becomes a color band. The smallest direction-color pattern.
Prerequisites: coordinates.
Construction: read the view direction the host already built. Reduce it to one scalar the author can name, such as a facing component. Send that scalar through hxSample_palette. Do not walk hxParamStops_palette by hand on this card. That manual walk is a different path and was not compared numerically to hxSample_palette.
Controls: which direction component becomes the scalar, and the ramp stops. The scalar is not a second camera.
Variations: a harder split between two bands, or a softer facing grade, stays this method. Those are proposed control changes.
Performance: one palette sample. No march. Not a frame time.
Troubleshooting: look first for color that follows facing rather than a painted UV. If the bands ignore the view, the scalar was taken from hx.uv or hx.fragCoord.
360: on equirectangular output hx.direction is hxUvToDir of hx.uv. On dome output the UV is derived from the ray. Say which one the scalar uses.
Combinations: palette-fog-light when the same ramp also carries fog. Avoid a second unrelated ramp on the same scalar.
Provenance: hx_starter, revision noted in the 2026-11-07 study, full short file, CC0-1.0 in the audit license table. Source-inspected.
Evidence: source-inspected. No compile, no pixels.
Adaptation: drop article uniforms and sampler lookups. The host already owns the direction.

### clock-pose
Kind: technique. Tags: camera.
Visual intent: a wrapped clock builds a basis, and the ray is hx.direction expressed in that basis. Travel reads as depth because the ray moves with the path, not because a print slides.
Prerequisites: coordinates.
Construction: build a path point from the clock. Name the period the author wrapped. Forward, right, and up come from that path. Put hx.direction into the basis. The host already produced the view ray. Speed of travel and the length of a repeated cell are different quantities.
Controls: path speed, the named wrap period, and how far ahead the forward aim looks. The wrap is continuity of the pose. It is not a fraction that speed must obey.
Variations: a straighter flight or a path that yaws in the horizontal plane stays this basis. A proposed change of the path shape is not a new card.
Performance: the basis is a few vectors. It does not by itself admit a loop. Not a frame time.
Troubleshooting: look first for forward motion in the path basis. An offset of hx.uv is a sliding print, not this pose.
360: the basis is 3D. It is not an offset of the panorama UV. Pole stretch of a print is a different card.
Combinations: repetition when the pose period should meet a field period. heightfield or sphere-trace as the world under the ray. Avoid storing the grade into the pose.
Provenance: hx_circuit_flight, CC0-1.0, source-inspected for the wrap. hx_dark_transit, MIT, diatribes, spherical adaptation by 360 Hextile, inspected for the path. The lighting module of hx_dark_transit was not the teaching text.
Evidence: source-inspected. No compile, no pixels.
Adaptation: a screen-space camera that stores position from frame to frame does not transfer. Drop article uniforms and preprocessor forms.

### playable-pose
Kind: technique. Tags: playable, camera.
Visual intent: the viewer offset sits on the clock basis. Helper names alone do not move the scene. The pointer matters only where the source reads it.
Prerequisites: coordinates, clock-pose.
Construction: require conventions/1 when the body uses it. The host then emits hxCameraPosition, hxCameraRotation, and hxCameraDirection. The direction helper is normalize of hxCameraRotation times the canonical direction. A null camera is zero position and identity rotation, as the shipped recipes guide states. Origin is the path point plus the basis times hxCameraPosition. The ray is the basis times hxCameraDirection of hx.direction. hx.direction stays the canonical view ray. Declare mouse/1 only when the body reads hx.pointer or the injected mouse member. Two audited assets declare mouse/1 and do not read hx.pointer or hx.mouse. A declaration is not playable input.
Controls: the existing convention camera sensitivity, path speed, and path radius. Do not invent a second camera uniform.
Variations: a faster pose or a wider offset stays this composition. The world under it belongs to another card.
Performance: the pose is a matrix and a vector. A later march has its own ceiling. This card promises no frame time.
Troubleshooting: look first for steering in the path basis. mouse/1 without a pointer read does not steer. An offset of hx.uv is a sliding print.
360: the playable offset is in the path basis, in 3D, not an offset of hx.uv. Shimmer while moving was not rendered.
Combinations: playable-flight. Avoid mouse/1 as decoration.
Provenance: the shipped recipes guide is the helper contract and was read. The shelf's playable composition was source-inspected under an anonymous alias that stays in the research. It is not repeated here.
Evidence: static-native camera helpers. Shelf pose is source-inspected. Capture and pixels were not tested.
Adaptation: a WASD sample that stores a screen-space camera does not transfer. Drop article samplers, uniforms, and preprocessor forms.

### heightfield
Kind: technique. Tags: heightfield.
Visual intent: a few smooth waves, an honest step, and one normal, so a ground has a horizon. Large shape first, fine grain second.
Prerequisites: coordinates.
Construction: trace a height of two or three smooth waves along hx.direction. When the waves are sines, the slope can be analytic, which is what hx_vaporwaves does, with a curvature-bounded step and a far plane of 64 in that asset as inspected on 2026-11-07. Otherwise use a central-difference normal and a step the author can justify. A step that grows with distance is one option in the terrain marching article. It is not a guarantee for an arbitrary height field. Name the step cap and the far plane. Stop adding octaves when the feature is under a pixel. The host gives the user shader no vertex stage and no geometry stage.
Controls: amplitude, wavelength, speed, step cap, and far plane. The admitted loop ceiling is not a float bound on the for loop.
Variations: broad dunes, a finer second wave, or a foggier grade are control changes. A water surface and clouds are future candidates, not variations of this card.
Performance: a fragment height field or a short march inside the admitted ceiling in sphere-trace. GPU Gems 3 terrain streaming was read only for density, gradient normals, and an occlusion fraction. Its mesh pipeline does not transfer. Admission is not a frame time.
Troubleshooting: look at the horizon band first. A chopped horizon points at the far plane and termination. Missing ground points at the step bound, the start, epsilon, and exhaustion before a ceiling change. Dunes in hx.uv are a panorama print, not this march.
360: a ground traced along hx.direction follows the ray. A decal in hx.uv is a print on the panorama. Dome output derives hx.uv from the dome ray, and hx.fragCoord stays on the dome raster. That difference was not rendered.
Combinations: palette-fog-light for one ramp and height fog. Avoid painting the dunes in hx.uv and also marching them.
Provenance: hx_vaporwaves, CC0-1.0, source-inspected through the trace. The grid helper at the end of that file was not finished. IQ terrain marching was read as a method article. The Book of Shaders fBm chapter was read as chapter prose with code blocks stripped. GPU Gems water was read for the sum-of-sines goals and the analytic slope, not the whole chapter. Named section. Full article, code stripped.
Evidence: source-inspected. No compile, no pixels.
Adaptation: drop vertex displacement and the article sampling and preprocessor forms. Keep the waves, the slope, the fog, and the admitted ceiling.

### sphere-trace
Kind: technique. Tags: march, performance.
Visual intent: a march whose loop ceiling is the admitted constant, plus a far plane and an optional early break. A miss is a color. Empty space may stay empty.
Prerequisites: coordinates.
Construction: step along the ray with a fresh scalar signed int. The ordinary ceiling is 256 trips and nesting of 2. An admitted temporal source may use 450 and 3. The bound and the step are constants. The body must not redeclare, assign, increment, or pass that name into a call. while and do are refused. User call nesting is at most 8, and recursion is refused. Several admitted loops can add steps. That sum is not an aggregate rejection and not a frame time. Name a far plane. An early break may stop on a hit. Read marches sit on or under the ordinary ceiling: dotted tunnel 96 and far 32, arcade lattice 224 and far 26, beam grid 256, digital tunnel 60. Those are 2026-11-07 observations. 256 is not a license to go higher.
Controls: the constant trip ceiling, the far plane, the step, and epsilon. The ceiling is not a float parameter and not a millisecond target.
Variations: a shorter early break or a quieter miss color stays this march. The field being marched belongs to another card.
Performance: the march is the cost, inside the admitted trip count. A Lipschitz or curvature bound is the author's job. Source caps remain 64 KiB raw and expanded, 32 files, include depth 16. Not a frame time.
Troubleshooting: look first for a hit that stays on the field, or a miss that is a color. For rays crossing a thin wall, inspect the step, epsilon, and termination. User code cannot discard.
360: the march follows a 3D ray. A corridor drawn as a fraction of hx.uv is a print, owned by graphic-print and poles-seam.
Combinations: repetition for a folded cell. palette-fog-light for one key and exponential fog. Avoid a second unbounded probe.
Provenance: hx_dotted_winding_tunnel, hx_arcade_lattice, hx_beam_grid, and hx_gyroid_raymarch were source-inspected. The audit license table records CC0-1.0 where it names those assets. hx_digital_tunnel is CC-BY-3.0, Jan Mróz (jaszunio15), adapted by 360 Hextile. Cite that asset. Do not paste it. Gallery with technique notes. Method article.
Evidence: source-inspected. No compile, no pixels. hx_menger_sponge_de is a named gap, not an example.
Adaptation: drop compute, mesh, and marching-cubes versions of the field. Drop article sampling and preprocessor forms.

### repetition
Kind: technique. Tags: repetition.
Visual intent: wrap traveled distance by the field period so the pose stays continuous and the folded cell stays in correspondence. The tile edge stays off the path when the wrap agrees with the cell.
Prerequisites: clock-pose.
Construction: choose a field period and wrap traveled distance by it. Speed and cell length stay different. Speed need not be a fraction of the cell. hx_beam_grid and hx_circuit_flight show that wrap. If radii vary, test neighbor cells, as the partial hx_sphere_tunnel read does. A nearest-cell shortcut is unsafe there. Reflection and main were not opened.
Controls: field period and travel speed, kept as separate numbers. A gap in the wrap is what shows the repeat.
Variations: a longer cell or a faster travel stays this wrap when the quantities stay distinct. Proposed looks that only change the field live on tunnel-flight.
Performance: wrapped indices are a continuity rule, separate from the march cost. Not a frame time.
Troubleshooting: look first for one visible repeat. For a pop in the repeat, inspect agreement between traveled-distance wrap and cell period.
360: a 3D cell follows the path. A repeat drawn on hx.uv is a panorama print and can show the seam. It stays attached to that print.
Combinations: tunnel-flight. Avoid a second unrelated repeat length in the same cell.
Provenance: hx_beam_grid and hx_circuit_flight, CC0-1.0, source-inspected for the wrap. hx_sphere_tunnel was partial. Smooth minimum was read as a method article. Catalog, not a Hextile recipe.
Evidence: source-inspected. Sphere-tunnel reflection and main unread. No compile, no pixels.
Adaptation: IQ's raymarching page notes that a camera rotation can hide domain repetition and that a cell id can vary instances. It does not establish locking a camera period to a cell.

### still-image
Kind: technique. Tags: image.
Visual intent: one declared still slot, sampled only through the host helpers, with an edge that does not sparkle. Alpha stays on the helper that was actually used.
Prerequisites: coordinates.
Construction: declare slot inputN before any sample. Codegen raises Missing image input when the name has no slot. A flat still calls hxSampleInputN with hx.uv (v=0 south). The frozen helper flips Y, so hx.mapUv flips again. Bilinear applies only when filter is linear. nearest and mipmap are nearest at lod 0 on that helper. hxSampleInputNGrad is the one-argument texture macro: implicit derivatives, no Y flip, no frozen sRGB decode, and no explicit gradient operands. User code cannot call textureGrad. Bake-worker bind_resource_textures, inspected 2026-11-08, builds mipmaps for a mipmap slot and does not flip the PNG row. Preview is unverified. Derivatives are unsafe across divergent flow. Schema names are linear, nearest, and mipmap. An equirectangular slot repeats U and clamps V. The inventory found none, and no sequence slot. Builtins had zero slots.
Controls: placement and scale on the chosen coordinate, the filter name, and the choice of frozen helper versus the Grad macro. Keep derivative calls in uniform control flow.
Variations: equator, a longitude shift, or a stronger warp are placement and scale. The frozen helper and hxSampleInputNGrad are not interchangeable looks. A sprite that follows hx.fragCoord is a different coordinate, already in coordinates.
Performance: one sample. No march is required. Not a frame time.
Troubleshooting: look first at the equator band and the sample edge. If an image is inverted, check whether a manual flip or hx.mapUv was passed where the frozen helper expects hx.uv. A missing slot cannot assemble. Divergent derivatives can sparkle.
360: hx.mapUv is the vertical flip of hx.uv. In the equirectangular wrapper both address the same panorama as hx.direction. Warping either warps the print and can stress the seam and the poles. It does not detach the print. A panorama sprite uses that UV. An output-raster sprite uses hx.fragCoord and means something else under the dome.
Combinations: still-on-sphere. Avoid treating hxSampleInputNGrad as a drop-in for the frozen helper.
Provenance: hx_warp_source has no provenance file in the audit. License not established. It calls hxSampleInput1 while the saved document lists zero slots. That call cannot assemble until a slot is declared. Compile was not run. Do not copy the slotless call forward. IQ filtering, bandlimiting, texture repetition, and filtering while raymarching were read as method articles.
Evidence: static-native helpers. Slotless hx_warp_source call observed. No compile, no fidelity render.
Adaptation: user code cannot call textureGrad or declare a sampler. An article URL is inspiration. It is not native compatibility.

### history
Kind: technique. Tags: history.
Visual intent: a trail that is the previous picture, sampled on purpose, or a separate feedback field stored before the grade. The next frame must not grade an already graded color again.
Prerequisites: coordinates.
Construction: sample hxPriorColor at hx.mapUv only when executable capabilities list frame-accumulation/1. Author schema 1, prior_frame_binding hxPriorColor, decay_parameter trail_decay, plus that sorted required capability. Do not author it when the id is absent. Do not add a get_capabilities flag, a pass graph, a history file, or a new tool. Replay from the start, at most 240 frames, full frame at most 2048 by 1024. Separate feedback uses hxSetFeedback and hxPriorFeedback, stores before the display grade, and is a different binding. One frame-accumulation shader's extra vertical flip is unresolved without a render and is not proof of orientation.
Controls: decay, and whether the stored field is the sample before exposure and palette. The replay caps are not sliders that raise the ceiling.
Variations: a longer trail or a trail of the ungraded field stays this binding. A new capture tool is out of scope.
Performance: the replay limits above. A march inside the sphere-trace ceiling, plus a 240-frame replay, may still miss a frame. Not a frame time.
Troubleshooting: look first at whether the stored field was graded. Storing the graded color makes the next frame grade it again. Sampling hxPriorColor at hx.uv instead of hx.mapUv fights the saved-map orientation.
360: intentional advection of a history field moves that print on purpose. That is the shader's update. It is not an automatic slide when the viewer turns.
Combinations: palette-fog-light after the field is known. playable-flight when the pose is deterministic per frame. Avoid feedback on shadertoy_image space. Separate feedback is refused there in the executor behavior the research recorded.
Provenance: the history limits are the shipped best-practices guide, static-native. The frame-accumulation example's extra flip was not rendered.
Evidence: static-native. No compile, no pixels. The orientation of the extra flip is an honest gap.
Adaptation: drop article buffers and sampler feedback. Use the host binding that is actually executable.

### palette-fog-light
Kind: technique. Tags: palette, lighting.
Visual intent: one ramp, exponential fog, and one key, so depth and a single color relationship read before any second lighting engine.
Prerequisites: coordinates.
Construction: paint with hxSample_palette at the end, after the field is known. Put height fog on the miss and on the far hit so speed has a depth cue. One key is enough. A painted bounce is enough. A manual walk of hxParamStops_palette is a different path and was not compared numerically to hxSample_palette. hx_kifs_foldbox and hx_flow_streamlines use that manual walk. Do not claim the two paths match.
Controls: ramp stops, fog density, and one key direction or height. The fog is a depth cue, not a scattering integral.
Variations: a foggier vista or a tighter key stays this grade. A second lighting engine is out of scope.
Performance: one ramp sample and a fog term. Not a frame time.
Troubleshooting: look first for depth in the fog and one color family in the ramp. If the grade is baked into stored history, the next frame grades it again.
360: fog follows the ray distance in 3D. A ramp painted as a function of hx.uv is a print, not this depth cue.
Combinations: heightfield, sphere-trace, and history when the stored field is ungraded. Avoid two ramps for the same scalar.
Provenance: shelf practice for one ramp and exponential height fog. IQ fog was read as a method article. IQ palettes, method article. GPU Gems 2 atmosphere was only the introduction and the opening of the scattering integral. Named section. A microfacet BRDF was not studied. The Self-Shadow 2025 page that was read is a syllabus. Overview.
Evidence: source-inspected where a Builtin grade was read. No compile, no pixels. The manual ramp walk was not compared numerically.
Adaptation: drop article uniform lights and preprocessor color macros. Keep one ramp and one fog term.

### graphic-print
Kind: technique. Tags: graphic.
Visual intent: cells, folds, or streamlines as a panorama print. The graphic is attached to the coordinate it names. It is not a marched corridor unless another card says so.
Prerequisites: coordinates.
Construction: pick the coordinate from coordinates and say it. Quantize or fold it into cells, sites, or a named streamline step. Send one scalar through one ramp at the end. hx_hopf_fibration uses angular sites and the gap between the nearest and the second nearest, with no march. hx_cyclic_ca quantizes hx.fragCoord. hx_flow_streamlines advects ink on a sphere from longitude and latitude of hx.mapUv. Hash and simplex helpers above that transport were identified and not line-read. That asset clamps line count and caps paint width. Those are observations, not a new ceiling.
Controls: cell size, site count, and line count, kept inside the admitted loop ceiling when a loop is used. A print with no loop has no trip count.
Variations: a coarser cell or a quieter second layer stays this print. A kaleidoscope of the same coordinate is a proposed fold, not a new id.
Performance: site or step counts that were read are observations of those assets. A loop still has to meet the sphere-trace ceiling. Not a frame time.
Troubleshooting: look first at whether the graphic uses hx.uv, hx.mapUv, or hx.fragCoord. On the equirectangular wrapper hx.fragCoord tracks hx.uv. On the dome wrapper it stays the output raster. Say which coordinate the graphic uses.
360: pole stretch and the seam belong to poles-seam. A print does not become a 3D march by stretching.
Combinations: poles-seam. direction-ramp when the scalar is facing rather than a cell. Avoid a second unrelated repeat length.
Provenance: hx_hopf_fibration, hx_cyclic_ca, and hx_flow_streamlines were source-inspected. Cite the audit license table for each asset rather than inventing a grant. Book of Shaders patterns was read as chapter prose. Full article, code stripped.
Evidence: source-inspected. No compile, no pixels.
Adaptation: drop article buffers and sampler palettes. Keep the coordinate explicit.

### poles-seam
Kind: technique. Tags: poles.
Visual intent: pole stretch, the seam, and a rear-hemisphere choice stay visible as composition, not as a hidden discard. A rear cut that removes half of a 360 picture must return a color.
Prerequisites: coordinates.
Construction: prefer hxDirToLonLat, hxAngularDistance, and hxTangentFrame. hxDirToLonLat falls back to +Z and returns longitude 0 when the horizontal radius is tiny. hxTangentFrame replaces a vanished east at the pole. A rear branch returns a color. User discard is refused. hx_cerulean_fractal_foam_2108550548479783327, re-read 2026-11-08, returns opaque black when the ray faces the rear. It does not use discard.
Controls: how wide the rear color is, and whether the front uses hx.direction or a longitude from hx.mapUv. The cerulean front is a perspective treatment of one hemisphere. That is an observation, not a required crop.
Variations: a softer pole, or a rear color other than black, is a proposed grade of the same branch. It is not a new card.
Performance: the helpers are a few vector operations. A marched rear field still uses the sphere-trace ceiling. Not a frame time.
Troubleshooting: look first at the poles and the seam of a print, and at the rear ray of a direction field. Opaque black on the rear is a color choice. It is not discard.
360: pole stretch is distortion of a print. It is not evidence that viewer motion drags the print. The seam is where panorama U meets. Dome hx.fragCoord is a different raster.
Combinations: graphic-print and still-image. Avoid a handwritten atan when the host helper already names the angle.
Provenance: hx_cerulean_fractal_foam_2108550548479783327, MIT on the Stage 1 license table, main read. Static-native pole helpers in NATIVE_ABI_CORE, inspected 2026-11-08.
Evidence: source-inspected for the rear branch. static-native for the helpers. No compile, no pixels.
Adaptation: drop article clip and discard. Return a color. Keep the host pole helpers.

### landscape-flythrough
Kind: recipe. Tags: heightfield, camera, lighting, palette.
Visual intent: a ground with a readable horizon, large dunes first and fine grain second, one color relationship, and travel that reads as depth. The horizon band is the subject. The poles are not.
Prerequisites: coordinates, clock-pose, heightfield, palette-fog-light.
Construction: build a clock pose wrapped to a named period. Express hx.direction in that basis. Trace the height field from heightfield. One ramp, and height fog on the miss and the far hit. Grade after the field is known. Do not bake the grade into stored history unless the picture is about trails.
Controls: wave amplitude, wavelength, speed, the sphere-trace ceiling, far plane, fog density, and ramp stops. An unsafe or over-large step can miss the ground. A shorter step can exhaust the ceiling before the far plane. A near far plane chops the horizon.
Variations: the same height field can read as broad dunes, a finer second wave, or a foggier vista. Those are control changes. They are not new cards. A water surface and clouds are future candidates, not variations of this recipe.
Performance: a fragment height field or a short march inside the admitted ceiling. The host has no vertex stage and no geometry stage. Admission is not a frame time.
Troubleshooting: look at the horizon band first. A chopped horizon points at the far plane. Missing ground points at the step, the start, epsilon, and exhaustion before any ceiling change. A hx.uv dune print is not this march.
360: the ground follows hx.direction. A hx.uv decal stretches at the poles and meets at the seam. Dome output was not rendered.
Combinations: repetition if a ridge period should match the flight period. Avoid painting the dunes as a fraction of hx.uv and also marching them in 3D.
Provenance: hx_vaporwaves, CC0-1.0, source-inspected through the trace, far plane 64 as inspected on 2026-11-07. IQ terrain marching and fog were read as method articles. GPU Gems water was read for the sum-of-sines goals and the analytic slope, not the whole chapter. GPU Gems 3 terrain was read only for density, gradient normals, and an occlusion fraction.
Evidence: source-inspected. No compile, no pixels.
Adaptation: screen-space ray construction from a flat tutorial is already done by hx.direction. Drop the vertex displacement and the article sampling forms. Keep the waves, the slope, the fog, and the admitted ceiling.

### tunnel-flight
Kind: recipe. Tags: march, repetition, camera, lighting.
Visual intent: an infinite corridor or lattice whose tile edge stays off the path, with speed readable as brightness falling off and one focal light. Empty dark space is part of the picture. Fill the frame only when the user asked for a packed lattice.
Prerequisites: clock-pose, repetition, sphere-trace, palette-fog-light.
Construction: one centerline, one path frame, one period wrap of traveled distance, and one march in the folded cell. Wrap traveled distance by the field period, as hx_beam_grid and hx_circuit_flight do. Put hx.direction into the path basis. March with the sphere-trace ceiling, an optional early break, and a named far plane. If radii vary, test neighbor cells. Partial hx_sphere_tunnel is that caution only. Light with one key and a rim, or a halo along the step, plus exponential fog, then one ramp. Fixed ceiling: 256 trips and 2 levels, or 450 and 3 only for an admitted temporal source. Several loops can add steps. No aggregate rejection and no frame-time promise. A miss is a color. No branch, portal, or collision response.
Controls: field period, travel speed, wall radius, fog density, the constant ceiling, and the far plane. Any speed can stay consistent when traveled distance is wrapped coherently by the field period. A step larger than the field's trust region can pass through a wall.
Variations: field and light change. No branch, portal, or collision. A miss stays a color. Neon rings, proposed: a rib at the field period plus the hx_digital_tunnel halo (60 steps, halo plus fog). Not a second shader and not a compile. Organic cave, proposed: smooth radius change on the same path. Partial hx_sphere_tunnel is the neighbor-cell caution only. Reflection and main stay unread. Not a relabel of hx_gyroid_raymarch. Mechanical lattice: source-inspected hx_arcade_lattice (224 steps, far 26, key and rim) and hx_beam_grid (256 steps, period wrap). No collision system. Twisting corridor, proposed: vary the centerline and the roll of its frame, same march. Fully read hx_dotted_winding_tunnel supports an analytic centerline and slope. Partial hx_sphere_tunnel instead bends the ray with a cubic flare and sine ripple, which is not this path frame.
Performance: the march is the cost, inside the admitted trip count. Wrapped indices are a separate continuity rule. Not a frame time.
Troubleshooting: look first for one visible repeat, a tile edge off the path, and speed as fog falloff. A pop means the traveled-distance wrap and the cell period disagree. Rays crossing walls point at the field bound, step, epsilon, and termination. A packed frame points at radius, spacing, and camera placement.
360: a 3D cell follows the path. A tunnel drawn as a fraction of hx.uv is a panorama print. It stretches at the poles, can show the seam, and stays on that print.
Combinations: graphic-print for a sign on the wall, using the same cell. Avoid a second unrelated repeat length.
Provenance: hx_beam_grid, hx_circuit_flight, hx_dotted_winding_tunnel, hx_arcade_lattice, and hx_gyroid_raymarch were source-inspected. The audit license table records CC0-1.0 where it names those assets. hx_dark_transit was inspected for the path and is MIT. hx_digital_tunnel is CC-BY-3.0, Jan Mróz (jaszunio15), adapted by 360 Hextile. Cite that asset. Do not paste it. hx_sphere_tunnel was partial. Identities are in the research table, inspected 2026-11-07. This page does not embed hashes.
Evidence: source-inspected. Sphere-tunnel reflection unread. No compile, no pixels.
Adaptation: drop compute, mesh, and marching-cubes versions of the field, and drop article sampling and preprocessor forms.

### still-on-sphere
Kind: recipe. Tags: image, poles, palette.
Visual intent: a photograph, a sprite, or a simple warped print that is clearly attached to the panorama, with a calm grade and an edge that does not sparkle. The subject sits on the equator band unless the user asked for a pole.
Prerequisites: coordinates, still-image.
Construction: declare one still slot before any sample. Sample with the frozen helper or the one-argument Grad macro, and do not treat them as the same look. Place the print on hx.uv unless the user asked for the output raster. Apply exposure and palette after the sample. Warping the coordinate warps the print. Do not copy a slotless sample forward.
Controls: placement and scale, edge mode, frozen reader versus the Grad macro, and the grade after the sample. A large warp can shimmer. User code cannot discard.
Variations: the same still can sit on the equator, shift in longitude, or take a stronger warp. Those are placement and scale. A sprite that follows hx.fragCoord is the coordinate choice in coordinates, not a new card.
Performance: one sample and one ramp. No march is required. Not a frame time.
Troubleshooting: use the still-image checks: equator, edge, a second flip through hx.mapUv, a missing slot, and divergent derivatives.
360: warping hx.uv or hx.mapUv warps the print and can stress the seam and the poles. It does not detach the print. Dome hx.fragCoord stays the dome raster.
Combinations: clock-pose for a slow U offset of the print. history only if the stored field is the sample before the grade. Avoid treating the Grad macro as a drop-in for the frozen helper.
Provenance: hx_warp_source, license not established, slot mismatch observed. IQ filtering articles named on still-image were read as method articles. The Book of Shaders patterns chapter was read as chapter prose.
Evidence: static-native helpers. Slotless call observed. No compile, no fidelity render.
Adaptation: choose the coordinate from coordinates. User code cannot declare a sampler. An article URL is inspiration, not native compatibility.

### playable-flight
Kind: recipe. Tags: playable, camera, march, performance.
Visual intent: the viewer steers along a path the shader already understands. The world has one silhouette, fog for depth, and a response to the pointer only where the source actually reads the pointer. Motion comes from the pose, not from a panorama print sliding under the camera.
Prerequisites: clock-pose, playable-pose, sphere-trace. Optional: history.
Construction: build the clock basis from clock-pose, then apply playable-pose. March with the admitted ceiling, an optional early break, and a named far plane. A miss is a quiet color, not a second scene, and not a discard. Declare mouse/1 only when the body reads the pointer. Optional history stores the field before the grade, and only when frame-accumulation/1 is executable. Capture must define the pose at each frame. This page does not add a capture tool.
Controls: path speed, path radius, camera sensitivity as the existing convention already defines it, the loop ceiling, far plane, and fog. The ceiling is not a millisecond target.
Variations: the same pose can run faster, sit on a wider path, or store history before the grade. The world under it is tunnel-flight or landscape-flythrough. History is optional and uses the existing caps. It is not a new capture tool.
Performance: a march inside the admitted ceiling, plus an optional 240-frame replay. Either may still miss a frame. Not a frame time.
Troubleshooting: look first for steering in the path basis. An hx.uv offset is a sliding print. mouse/1 without a pointer read does not steer. Storing the graded color grades it again next frame. Capture and pixels were not tested.
360: the playable offset is applied in the path basis, in 3D. An intentional advection of a history field moves that print on purpose. It is not an automatic slide when the viewer turns.
Combinations: tunnel-flight or landscape-flythrough as the world under this pose. Avoid mouse/1 as decoration. Avoid storing the graded color in the feedback loop.
Provenance: the shipped recipes guide was read for the helper contract. The shelf pose stays under its anonymous alias and is not repeated here. PBRT's camera chapter was the introduction only (named section), not a Hextile camera.
Evidence: static-native camera helpers. Shelf pose is source-inspected. Capture and pixels were not tested.
Adaptation: a sample that stores position in a screen-space camera from frame to frame does not transfer. Drop article samplers, uniforms, and preprocessor forms.

## Gaps

Absent on purpose, until a later reading: a microfacet BRDF, the unread GPU Gems and Khronos chapters, the Perlin and Neyret paper, clouds, a water surface, sequence and equirectangular slots as populated examples, unread bodies such as hx_escher_droste_map and hx_fullerene_projection, the partial hx_menger_sponge_de, project inventory, compile, pixels, export, and cube preview.
