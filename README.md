# Tuya Smart Life Local

Tích hợp tùy chỉnh cho Home Assistant: đăng nhập bằng tài khoản Tuya thường, lấy thiết bị từ mobile API, rồi điều khiển local qua LAN khi thiết bị hỗ trợ Tuya local protocol.

Không cần dự án Tuya IoT Cloud. Không cần nhập `app_id`, `app_secret`, certificate fingerprint hoặc native signing key.

## Cài đặt nhanh

Mở kho mã này trong HACS:

[![Mở kho mã trong HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=home-assistant-tools&repository=tuya-smart-life&category=integration)

Sau khi tải xong và restart Home Assistant, mở màn hình cấu hình:

[![Bắt đầu thiết lập integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=tuya_smart_life_local)

## Thiết lập

1. Vào **Settings -> Devices & services**.
2. Bấm **Add integration**.
3. Tìm **Tuya Smart Life Local**.
4. Chọn **Ứng dụng** là **Tuya** hoặc **Smart Life**.
5. Nhập email/số điện thoại Tuya và mật khẩu.
6. Chọn các nhà muốn đồng bộ, hoặc để trống nếu chưa muốn tải thiết bị.

Với email, integration không hỏi mã vùng. Với số điện thoại Việt Nam, integration vẫn dùng mặc định `84` nội bộ.

## Tài liệu

- [Cài đặt, đăng nhập và cập nhật](docs/setup.md)
- [Cơ chế điều khiển local](docs/local-control.md)
- [Thiết bị công tắc, DPS và cảm biến](docs/devices-switch.md)
- [Lịch và hẹn tắt thiết bị](docs/devices-schedule.md)
- [Thiết bị IR, điều hòa, media remote](docs/devices-ir.md)
- [MQTT cloud tự suy ra thông tin đăng nhập](docs/mqtt-auto-credentials.md)
- [Khóa Wi-Fi và mở khóa](docs/devices-lock.md)
- [Xử lý sự cố](docs/troubleshooting.md)
- [Reverse engineering, MITM, signing, crypto](docs/reverse-engineering.md)
- [Bản đồ API Android Tuya Smart](docs/tuya-smart-android-api-findings.md)
- [Ghi chú phát hành](docs/releases/v0.1.61.md)

## Ghi chú nhanh

- Home Assistant nên ở cùng LAN/broadcast domain với thiết bị hoặc hub Tuya.
- Thiết bị Wi-Fi/root có IP local sẽ có cảm biến IP local.
- Chỉ hub mới hiển thị online/offline cloud.
- MQTT không cần nhập thủ công; tích hợp tự suy ra từ phiên đăng nhập mobile nếu Tuya trả đủ dữ liệu.
- Có action hẹn tắt thiết bị Tuya theo số phút và action xóa toàn bộ timer/lịch cloud của thiết bị.
- IR là điều khiển một chiều, nên trạng thái trong HA là trạng thái ước lượng từ lệnh cuối.

APK, source decompile, capture thật, thông tin đăng nhập, session token và local key không được commit vào kho mã.
