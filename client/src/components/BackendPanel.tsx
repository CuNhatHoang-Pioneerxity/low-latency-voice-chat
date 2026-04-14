import React from 'react';
import './BackendPanel.css';

export interface OrderItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
  total: number;
}

export interface BackendUpdate {
  type: 'order_update' | 'order_confirmed' | 'menu_display' | 'payment_qr';
  order?: OrderItem[];
  total?: number;
  items?: Array<{ id: string; name: string; price: number; category: string }>;
  category?: string;
  amount?: number;
  qr_data?: string;
}

interface BackendPanelProps {
  updates: BackendUpdate[];
}

const formatPrice = (price: number): string => {
  return `${price.toLocaleString()} VND`;
};

const BackendPanel: React.FC<BackendPanelProps> = ({ updates }) => {
  // Get the latest order state
  const latestOrder = updates
    .filter(u => u.type === 'order_update' || u.type === 'order_confirmed')
    .reverse()[0];
  
  const paymentQR = updates
    .filter(u => u.type === 'payment_qr')
    .reverse()[0];

  // Get the latest menu display
  const latestMenu = updates
    .filter(u => u.type === 'menu_display')
    .reverse()[0];

  return (
    <div className="backend-panel">
      <div className="backend-header">
        <h3>Order Status</h3>
        {latestOrder?.type === 'order_confirmed' && (
          <span className="confirmed-badge">Confirmed</span>
        )}
      </div>

      <div className="backend-content">
        {latestOrder?.order && latestOrder.order.length > 0 ? (
          <div className="order-list">
            {latestOrder.order.map((item) => (
              <div key={item.id} className="order-item">
                <span className="item-name">{item.name}</span>
                <span className="item-qty">x{item.quantity}</span>
                <span className="item-price">{formatPrice(item.total)}</span>
              </div>
            ))}
            <div className="order-total">
              <span>Total</span>
              <span className="total-amount">
                {formatPrice(latestOrder.total || 0)}
              </span>
            </div>
          </div>
        ) : (
          <div className="empty-order">
            <p>No items in order</p>
            <span>Speak to add items</span>
          </div>
        )}

        {latestMenu?.items && latestMenu.items.length > 0 && (
          <div className="menu-section">
            <h4>Menu {latestMenu.category ? `- ${latestMenu.category}` : ''}</h4>
            <div className="menu-list">
              {latestMenu.items.map((item) => (
                <div key={item.id} className="menu-item">
                  <span className="menu-item-name">{item.name}</span>
                  <span className="menu-item-price">{formatPrice(item.price)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {paymentQR && (
          <div className="payment-section">
            <h4>Payment</h4>
            <div className="payment-amount">
              {formatPrice(paymentQR.amount || 0)}
            </div>
            <div className="qr-image-container">
              <img src="/QR.png" alt="Payment QR Code" className="qr-image" />
            </div>
          </div>
        )}
      </div>

      <div className="backend-footer">
        <h4>Activity Log</h4>
        <div className="activity-log">
          {updates.slice(-5).reverse().map((update, idx) => (
            <div key={idx} className="log-entry">
              <span className="log-type">{update.type.replace(/_/g, ' ')}</span>
            </div>
          ))}
          {updates.length === 0 && (
            <div className="log-empty">No activity yet</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default BackendPanel;
