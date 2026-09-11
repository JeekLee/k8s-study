"use client";

import { useEffect, useState } from "react";

// 브라우저에서 접근하므로 Ingress 경로를 쓴다.
// 쿠버네티스 Service DNS 이름(order.default.svc)은 클러스터 내부에서만 유효하다.
const ORDER_API = process.env.NEXT_PUBLIC_ORDER_API ?? "/api/order";
const INVENTORY_API = process.env.NEXT_PUBLIC_INVENTORY_API ?? "/api/inventory";

type Order = { id: string; sku: string; qty: number; status: string };

export default function Page() {
  const [stock, setStock] = useState<Record<string, number>>({});
  const [orders, setOrders] = useState<Order[]>([]);
  const [sku, setSku] = useState("SKU-001");
  const [qty, setQty] = useState(1);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [s, o] = await Promise.all([
        fetch(`${INVENTORY_API}/stock`).then((r) => r.json()),
        fetch(`${ORDER_API}/orders`).then((r) => r.json()),
      ]);
      setStock(s.stock ?? {});
      setOrders(Array.isArray(o) ? o : []);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000); // 사가 진행을 지켜본다
    return () => clearInterval(t);
  }, []);

  async function createOrder() {
    await fetch(`${ORDER_API}/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sku, qty }),
    });
    refresh();
  }

  return (
    <main>
      <h1>주문 데모</h1>
      {error && <p style={{ color: "crimson" }}>오류: {error}</p>}

      <h2>재고</h2>
      <ul>
        {Object.entries(stock).map(([k, v]) => (
          <li key={k}>
            {k}: {v}
          </li>
        ))}
      </ul>

      <h2>주문하기</h2>
      <p>
        <input value={sku} onChange={(e) => setSku(e.target.value)} />
        <input
          type="number"
          min={1}
          value={qty}
          onChange={(e) => setQty(Number(e.target.value))}
          style={{ width: 60, marginLeft: 8 }}
        />
        <button onClick={createOrder} style={{ marginLeft: 8 }}>
          주문
        </button>
      </p>

      <h2>주문 목록</h2>
      <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>SKU</th>
            <th>수량</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{o.sku}</td>
              <td>{o.qty}</td>
              <td>{o.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
