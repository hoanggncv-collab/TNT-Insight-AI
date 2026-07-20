
# TNT Insight AI — MVP v0.1

Ứng dụng Streamlit để phân tích dữ liệu TikTok Shop theo:

- Tổng đơn
- User cancel
- Delivery Fail (System)
- DFR = System / (Tổng đơn - User)
- Order Loss
- Region
- Creator / Product Cards
- Product
- Pricing
- Timeline tài khoản quảng cáo theo ngày tạo đơn

## Chạy trên máy

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Sau đó mở địa chỉ Streamlit hiển thị trong Terminal.

## Deploy online bằng Streamlit Community Cloud

1. Tạo repository private trên GitHub.
2. Upload toàn bộ file trong thư mục này lên repository.
3. Vào Streamlit Community Cloud.
4. Chọn repository và file chạy `app.py`.
5. Deploy.

## Cách dùng

1. Upload file `All Order.xlsx`.
2. Mở mục **Kiểm tra / chỉnh mapping cột**.
3. Xác nhận:
   - Order ID
   - Order Created Time
   - Cancel By
   - Region
   - Creator Handle
   - Product Name
   - Seller SKU
   - Price
4. Xem các tab phân tích.
5. Trong tab **BC Timeline**, nhập các khoảng ngày và tên tài khoản quảng cáo.
6. Xuất Excel nếu cần.

## Lưu ý

- Mỗi Order ID được tính một lần.
- Mốc thời gian timeline dùng **Order Created Time**.
- `User` và `System` được đọc từ cột `Cancel By` (hoặc cột được map tương đương).
- TikTok có thể thay đổi tên cột; app có phần mapping để xử lý.
