/**
 * Yahoo Snake Draft — MAIN world interceptor.
 *
 * Runs in the page's MAIN world, injected by the manifest content_scripts entry
 * with "world": "MAIN" (NOT an inline <script> tag — Yahoo's CSP blocks those;
 * extension content scripts are exempt from page CSP). The DOM poller in
 * yahoo_snake_draft.js runs in the ISOLATED world and can't see the page's
 * console, so this MAIN-world file does the interception and forwards frames
 * across the world boundary via a window CustomEvent.
 *
 * Intercepts Yahoo's own console.error pick logging:
 *   ['0', league, draft, pick_number, yahoo_player_id] -> a snake pick
 *
 * Yahoo logs the ['0'] frame only for YOUR OWN picks (same as ['B']/['N'] in
 * auction). Dispatched as '__yahoo_snake_pick__' for the isolated poller.
 */
;(function () {
  if (window.__draftmind_snake__) return

  const _origError = console.error
  console.error = function (...args) {
    if (Array.isArray(args[0]) && args[0][0] === '0') {
      window.dispatchEvent(
        new CustomEvent('__yahoo_snake_pick__', { detail: args[0] })
      )
    }
    return _origError.apply(console, args)
  }
  window.__draftmind_snake__ = true
})()
