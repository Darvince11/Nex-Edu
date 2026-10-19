"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Alert, Button, Loading, PageHeader } from "@/components/ui";
import { api, download, type Payment } from "@/lib/api";
import { cedis } from "@/lib/format";

export default function PaymentReturnPage() {
  return (
    <Suspense fallback={<Loading />}>
      <PaymentReturn />
    </Suspense>
  );
}

/** Where Paystack / Flutterwave send the parent back. We ask our server to
 * confirm with the provider; the redirect itself proves nothing. */
function PaymentReturn() {
  const reference = useSearchParams().get("reference") ?? "";
  const result = useQuery({
    queryKey: ["payment-return", reference],
    enabled: Boolean(reference),
    retry: 2,
    queryFn: async () => {
      const [payment] = await api.get<Payment[]>(
        `/api/v1/finance/payments?reference=${encodeURIComponent(reference)}`,
      );
      if (!payment) throw new Error("We couldn't find this payment.");
      return api.post<Payment>(`/api/v1/finance/payments/${payment.id}/verify`);
    },
  });

  return (
    <>
      <PageHeader title="Payment" />
      {result.isPending && <Loading />}
      {result.error && <Alert tone="error">{(result.error as Error).message}</Alert>}
      {result.data?.status === "success" && <Paid payment={result.data} />}
      {result.data && result.data.status === "pending" && (
        <Alert tone="info">
          Your payment is still being confirmed. This can take a minute for mobile money. You'll get a
          notification when it's done.
        </Alert>
      )}
      {result.data && ["failed", "abandoned"].includes(result.data.status) && (
        <Alert tone="error">
          The payment didn't go through. No money was taken.{" "}
          <Link href="/fees" className="underline">
            Try again
          </Link>
          .
        </Alert>
      )}
    </>
  );
}

function Paid({ payment }: { payment: Payment }) {
  return (
    <div className="flex flex-col gap-3">
      <Alert tone="success">
        Payment of {cedis(payment.amount_received_pesewas)} received for {payment.student_name}. Receipt{" "}
        {payment.receipt_number}.
      </Alert>
      <div className="flex gap-2">
        <Button
          onClick={() =>
            download(`/api/v1/finance/payments/${payment.id}/receipt`, `${payment.receipt_number}.pdf`)
          }
        >
          Download receipt
        </Button>
        <Link href="/fees" className="btn-secondary">
          Back to fees
        </Link>
      </div>
    </div>
  );
}
