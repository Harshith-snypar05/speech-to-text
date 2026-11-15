/**
 * Loads Cashfree's own JS SDK and hands it the session id our backend returned from
 * POST /v1/billing/checkout. Unlike Stripe, Cashfree has no plain redirect URL -- the SDK itself
 * does the redirect to its hosted checkout once given a payment/subscription session id.
 */
declare global {
  interface Window {
    Cashfree?: (opts: { mode: "sandbox" | "production" }) => {
      checkout: (opts: { paymentSessionId: string; redirectTarget?: "_self" | "_blank" | "_modal" }) => Promise<unknown>;
      subscriptionsCheckout: (opts: { subsSessionId: string; redirectTarget?: "_self" | "_blank" | "_modal" }) => Promise<unknown>;
    };
  }
}

let sdkLoad: Promise<void> | null = null;

function loadSdk(): Promise<void> {
  if (window.Cashfree) return Promise.resolve();
  if (!sdkLoad) {
    sdkLoad = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://sdk.cashfree.com/js/v3/cashfree.js";
      s.onload = () => resolve();
      s.onerror = () => { sdkLoad = null; reject(new Error("Could not load the payment SDK. Check your connection and try again.")); };
      document.head.appendChild(s);
    });
  }
  return sdkLoad;
}

export async function startCashfreeCheckout(result: { kind: "order" | "subscription"; session_id: string; live: boolean }) {
  await loadSdk();
  const cashfree = window.Cashfree!({ mode: result.live ? "production" : "sandbox" });
  if (result.kind === "order") {
    await cashfree.checkout({ paymentSessionId: result.session_id, redirectTarget: "_self" });
  } else {
    await cashfree.subscriptionsCheckout({ subsSessionId: result.session_id, redirectTarget: "_self" });
  }
}
