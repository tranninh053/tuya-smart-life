# Xử lý sự cố

## Đăng nhập báo `cannot_connect`

- Kiểm tra email/số điện thoại/mật khẩu.
- Kiểm tra Home Assistant có internet.
- Integration tự thử các endpoint mobile API; không cần chọn vùng thủ công.
- Nếu Smart Life yêu cầu MFA/secondary verification, flow hiện tại có thể chưa xử lý được.

## Entity unavailable hoặc local control lỗi

- Kiểm tra Home Assistant và thiết bị/hub cùng LAN/broadcast domain.
- Nếu HA chạy Docker/TrueNAS, dùng network mode nhận được broadcast LAN.
- Integration cần UDP `6666`, `6667`, `6699`, `7000` và TCP tới thiết bị/hub.
- Cross-subnet/VLAN/WAN discovery chưa hỗ trợ tự động.
- Nếu mobile API trả IP public/WAN, integration bỏ qua và chờ broadcast/LAN scan tìm IP private.
- Lỗi `Check device key or version` thường là local key/protocol/IP chưa khớp hoặc stream local đang tranh kết nối.

## IR remote hoặc IR climate không xuất hiện

- Kiểm tra nhà được chọn có IR hub cùng LAN với Home Assistant.
- Chạy:

  ```bash
  python3 tools/tuya_mobile_login.py --action ir --home-id <home-id>
  ```

- Nếu Tuya chỉ trả raw button, integration tạo button thay vì climate/fan/light/media_player.
- Nếu API và scenes đều không có `actionDps`/`executorProperty`, dữ liệu hiện tại chưa đủ để bấm IR local. Tạo scene trong app Tuya cho nút cần dùng có thể giúp app lưu payload.

## Chọn sai nhà

Mở options của integration và bỏ nhà đó khỏi danh sách. Có thể chọn không nhà nào nếu chỉ muốn giữ login/home-list mà chưa tải thiết bị.
