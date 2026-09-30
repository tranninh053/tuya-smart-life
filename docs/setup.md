# Cài đặt, đăng nhập và cập nhật

## Cài đặt qua HACS

1. Mở HACS trong Home Assistant.
2. Vào **Integrations**.
3. Chọn **Custom repositories**.
4. Nhập kho mã:

   ```text
   https://github.com/home-assistant-tools/tuya-smart-life
   ```

5. Chọn category/type là **Integration**.
6. Tải **Tuya Smart Life Local**.
7. Restart Home Assistant.

Nút thêm nhanh nằm trong [README](../README.md).

## Đăng nhập

1. Vào **Settings -> Devices & services**.
2. Bấm **Add integration**.
3. Tìm **Tuya Smart Life Local**.
4. Chọn **Ứng dụng** là **Tuya** hoặc **Smart Life**.
5. Nhập email/số điện thoại Tuya và mật khẩu.
6. Chọn nhà cần đồng bộ.

Với email, màn đăng nhập không hỏi mã vùng. Với số điện thoại Việt Nam, integration vẫn dùng mặc định `84` nội bộ và thử biến thể bỏ số `0` đầu vì Tuya mobile API nhận country code riêng.

Integration tự thử các endpoint mobile API của Tuya/Smart Life, không cần chọn vùng thủ công.

## Cập nhật

1. Mở HACS.
2. Mở repository **Tuya Smart Life Local**.
3. Bấm **Update information** nếu chưa thấy bản mới.
4. Bấm **Download/Redownload**.
5. Restart Home Assistant.

Khi đổi danh sách nhà trong options, integration reload để Home Assistant dọn entity/device cũ và tạo lại entity mới.
