# TDD & Testing Guidelines (Deep Modules & Matt Pocock Style)

**Mục tiêu**: Đảm bảo 100% core logic của hệ thống DataLuatVN (RAG Gen 3, Agents) được kiểm thử kỹ lưỡng, tránh "Ball of Mud" (mã nguồn rối rắm). 

## 1. Nguyên tắc Red-Green-Refactor
Mỗi khi phát triển tính năng mới hoặc sửa lỗi:
1. **Red**: Viết 1 test case thất bại (nhưng định nghĩa rõ ràng mong muốn đầu ra).
2. **Green**: Viết mã nguồn đơn giản nhất (có thể hardcode, bừa bãi) để test pass.
3. **Refactor**: Tái cấu trúc mã nguồn cho sạch sẽ, áp dụng Facade/Deep Modules, đảm bảo test vẫn pass.

## 2. Tiêu chuẩn Test Case
- Tên file test phải bắt đầu bằng `test_`.
- Tên hàm test phải bắt đầu bằng `test_` và phản ánh rõ mục đích (VD: `test_persona_switcher_detects_judge_role`).
- Cấu trúc **Arrange - Act - Assert (AAA)**:
  - **Arrange**: Chuẩn bị dữ liệu (mock data, query).
  - **Act**: Gọi hàm cần test.
  - **Assert**: Kiểm tra kết quả. Đảm bảo sử dụng `assert` với thông báo lỗi rõ ràng.

## 3. Khuyến nghị Kỹ thuật
- Sử dụng `pytest.mark.anyio` cho các hàm bất đồng bộ (`async`).
- Tránh phụ thuộc vào DB thực (sử dụng mocking hoặc DB in-memory SQLite).
- Các hệ thống gọi LLM bên ngoài (như `LLMGateway`) **phải được mock** để tránh hao tốn API quota và đảm bảo tốc độ chạy test < 1s/test.

## 4. Kỷ luật Debug (Smart Debugging)
- Tuyệt đối không "đoán mò" và sửa mù quáng.
- Khi gặp lỗi, luôn thu thập stack trace đầy đủ (đã sử dụng Logfire).
- Phân tích nguyên nhân gốc rễ (Root Cause) trước khi thay đổi logic. Cập nhật test case để tái hiện lỗi đó, sau đó mới tiến hành sửa mã nguồn.
