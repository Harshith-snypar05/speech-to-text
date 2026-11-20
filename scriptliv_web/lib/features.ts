/**
 * Master switch for everything that shows a subscription model: plans, prices, add-ons, membership details,
 * cancel/keep membership, payment history, upgrade prompts and the /pricing page.
 *
 * Off by default. To bring it all back, set NEXT_PUBLIC_SHOW_SUBSCRIPTIONS=1 at build time (Vercel env) and redeploy.
 * The Flutter app has the matching switch in `lib/config/app_config.dart` (`SL_SHOW_SUBSCRIPTIONS`).
 */
export const SHOW_SUBSCRIPTIONS = process.env.NEXT_PUBLIC_SHOW_SUBSCRIPTIONS === "1";
