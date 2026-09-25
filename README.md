# 🎓 Hệ Thống Quản Lý Sinh Viên & Đào Tạo Tín Chỉ (HTQLSV)
### 🏛️ Student Management System (Python Tkinter & MySQL)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![GUI](https://img.shields.io/badge/GUI-Tkinter%2Fttk-orange.svg)](https://docs.python.org/3/library/tkinter.html)
[![Database](https://img.shields.io/badge/Database-MySQL%208.0%2B-blue.svg?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![Testing](https://img.shields.io/badge/Tests-130%20passed%20(pytest)-brightgreen.svg?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 Giới thiệu tổng quan

**Hệ Thống Quản Lý Sinh Viên (HTQLSV)** là ứng dụng máy tính (Desktop Application) toàn diện hỗ trợ quản trị trường đại học/cao đẳng theo mô hình đào tạo tín chỉ. Ứng dụng được xây dựng bằng ngôn ngữ **Python** kết hợp thư viện đồ họa **Tkinter/ttk** và hệ quản trị cơ sở dữ liệu quan hệ **MySQL**.

Hệ thống giải quyết trọn vẹn bài toán quản lý đào tạo hiện đại với mô hình phân quyền chặt chẽ, kiểm soát phiên người dùng (Session Management), xử lý tranh chấp đăng ký lớp thời gian thực, quản lý học phí và thống kê đa chiều.

---

## ✨ Điểm nổi bật & Tính năng chính

### 1. 🛡️ Quản trị viên (Admin)
- **Cơ cấu tổ chức & Đào tạo:**
  - Quản lý Khoa (Faculties), Ngành học (Programs), Khóa tuyển sinh (Batches), Lớp hành chính (Admin Classes).
  - Quản lý Năm học (Academic Years), Học kỳ (Semesters), Danh mục Môn học (Subjects) và Lớp học phần (Class Sections).
- **Quản lý Hồ sơ & Trạng thái Sinh viên:**
  - Cập nhật thông tin sinh viên, đổi trạng thái học tập (*Đang học, Bảo lưu, Thôi học, Tốt nghiệp*).
  - Tự động ghi nhận lịch sử thay đổi (Audit History) đảm bảo tính toàn vẹn và minh bạch qua Transaction.
- **Báo cáo & Thống kê thông minh (Dashboard):**
  - Thống kê trực quan số lượng sinh viên đa chiều: theo Trạng thái, Khoa, Ngành, Khóa tuyển sinh và Lớp hành chính.
  - Bộ lọc đa cấp linh hoạt và tính năng **Xuất báo cáo CSV** (hỗ trợ chuẩn Unicode UTF-8 BOM, an toàn chống injection công thức).

### 2. 👨‍🏫 Giảng viên (Lecturer)
- Tra cứu danh sách các Lớp học phần được phân công giảng dạy theo từng học kỳ.
- Xem danh sách sinh viên đăng ký của từng lớp.
- Nhập và cập nhật bảng điểm (Điểm quá trình/giữa kỳ, Điểm thi kết thúc/cuối kỳ) kèm cơ chế chống nhầm lẫn dữ liệu giữa các lớp.

### 3. 🎓 Sinh viên (Student)
- **Đăng ký học phần tín chỉ trực quan:**
  - Tự động kiểm tra điều kiện tiên quyết và thời gian mở cổng đăng ký.
  - **Chống vượt sĩ số**: Ràng buộc giới hạn số lượng sinh viên tối đa của lớp học phần.
  - **Chống trùng môn**: Ngăn chặn đăng ký trùng môn học trong cùng một học kỳ.
  - **Chống trùng lịch học**: Tự động phát hiện và cảnh báo xung đột thời khóa biểu giữa các lớp học phần.
- **Tra cứu & Theo dõi:**
  - Xem Thời khóa biểu / Lịch học chi tiết theo tuần/học kỳ.
  - Tra cứu Bảng điểm tổng hợp và điểm tích lũy học phần.
  - Theo dõi công nợ, định mức học phí tín chỉ và lịch sử thanh toán học phí.

---

## 🏗️ Kiến trúc Cơ sở Dữ liệu & Đào tạo Tín chỉ

Hệ thống được thiết kế theo chuẩn cơ sở dữ liệu quan hệ với các ràng buộc khóa ngoại (Foreign Keys) nghiêm ngặt:

```
[Khoa (Faculties)] ──< [Ngành (Programs)] ──< [Lớp Hành Chính] ──< [Sinh Viên]
                            │                                            │
[Khóa Tuyển Sinh] ──────────┘                                            │
                                                                         │
[Năm Học] ──< [Học Kỳ (Semesters)]                                       │
                    │                                                    │
[Môn Học] ────< [Lớp Học Phần (Class Sections)]                          │
                    │                                                    │
             [Lượt Đăng Ký (Enrollments)] >──────────────────────────────┘
                    │
             [Học Phí / Thanh Toán (Payments)]
```

### Điểm cải tiến kiến trúc:
- **Tách biệt Môn học & Lớp học phần:** Môn học định nghĩa khung kiến thức và số tín chỉ; Lớp học phần gắn với giảng viên, phòng học, lịch biểu và học kỳ cụ thể.
- **Phân định rõ Lớp hành chính & Lớp học phần:** Sinh viên thuộc về một Lớp hành chính cố định nhưng có thể đăng ký nhiều Lớp học phần khác nhau cùng các bạn khác khoa/ngành.
- **Quản lý phiên đăng nhập (Session):** Kiểm soát quyền hạn chặt chẽ ở tầng giao diện, tự động thu hồi phiên khi đăng xuất hoặc đóng ứng dụng.

---

## 🛠️ Công nghệ sử dụng

- **Ngôn ngữ:** Python 3.10+
- **Giao diện Desktop (GUI):** Tkinter, ttk (Custom Themes & Dialogs)
- **Cơ sở dữ liệu:** MySQL Server 8.0+
- **Thư viện kết nối & Bảo mật:**
  - `mysql-connector-python`: Giao tiếp Database hiệu năng cao
  - `bcrypt`: Mã hóa và băm mật khẩu người dùng
- **Kiểm thử tự động:** `pytest` (Bộ test suite 130 tests kiểm tra logic nghiệp vụ, transaction, race condition và khóa đồng thời)

---

## 🚀 Hướng dẫn Cài đặt & Khởi chạy

### 1. Yêu cầu hệ thống
- Đã cài đặt **Python 3.10+** ([Tải tại python.org](https://www.python.org/))
- Đã cài đặt **MySQL Server 8.0+** ([Tải MySQL Community Server](https://dev.mysql.com/downloads/mysql/))

### 2. Clone mã nguồn
```bash
git clone https://github.com/ngocphuoc06/htqlsv.git
cd htqlsv
```

### 3. Cài đặt các thư viện phụ thuộc
Khuyến nghị tạo môi trường ảo (virtual environment):
```bash
# Tạo và kích hoạt môi trường ảo
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat

# Cài đặt thư viện
pip install -r requirements.txt
```

### 4. Cấu hình Cơ sở Dữ liệu
1. Mở MySQL và tạo cơ sở dữ liệu `admin_db`:
   ```sql
   CREATE DATABASE admin_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Tạo file `config.ini` từ file mẫu `config.ini.example`:
   ```ini
   [database]
   host = localhost
   user = root
   password = your_mysql_password
   database = admin_db
   port = 3306
   ```

### 5. Khởi tạo cấu trúc & Dữ liệu mẫu (Seed Data)
Di chuyển vào thư mục mã nguồn và chạy script tạo bảng & nạp dữ liệu:
```bash
cd "StudentManagementSystem/Student-management-system/Student Management System"
python insert_Data.py
```

### 6. Khởi chạy ứng dụng
```bash
python main.py
```

---

## 🔑 Tài khoản Đăng nhập Mặc định (Thử nghiệm)

| Vai trò (Role) | Tên đăng nhập (Username) | Mật khẩu mặc định | Ghi chú |
|---|---|---|---|
| **Admin** | `admin` | `admin123` | Quản trị toàn hệ thống |
| **Giảng viên** | `gv_nam` | `123456` | Giảng viên phụ trách lớp học phần |
| **Sinh viên** | `20210001` | `123456` | Sinh viên đăng ký học phần |

---

## 🧪 Kiểm thử (Testing)

Dự án tích hợp bộ kiểm thử toàn diện với **130 bài kiểm thử** (Pytest) bao gồm kiểm thử hồi quy, kiểm thử phiên làm việc, kiểm tra giao dịch (Transaction Rollback) và xử lý tranh chấp khóa (Data Lock Contention):

```bash
# Cài đặt thư viện dev
pip install -r requirements-dev.txt

# Thiết lập biến môi trường cấu hình test database (PowerShell)
$env:SMS_TEST_MYSQL_JSON='{"user":"root","password":"your_password","host":"localhost"}'

# Chạy test suite
python -m pytest -q tests --tb=short
```

---

## 📂 Cấu trúc thư mục dự án

```text
HTQLSV/
├── StudentManagementSystem/
│   └── Student-management-system/
│       ├── Student Management System/    # Mã nguồn chính
│       │   ├── gui/                      # Giao diện, Services & Database layer
│       │   │   ├── interface.py          # Cửa sổ giao diện chính (Admin, GV, SV)
│       │   │   ├── database.py           # Tương tác MySQL database
│       │   │   ├── services.py           # Xử lý logic nghiệp vụ đào tạo
│       │   │   ├── session.py            # Quản lý phiên đăng nhập
│       │   │   ├── scheduling.py         # Kiểm tra xung đột lịch học
│       │   │   ├── migration.py          # Cơ chế cập nhật schema tự động
│       │   │   └── config.py             # Đọc file cấu hình config.ini
│       │   ├── main.py                   # Điểm khởi chạy ứng dụng (Entry point)
│       │   ├── insert_Data.py            # Script khởi tạo bảng & dữ liệu mẫu
│       │   └── migrate_passwords.py      # Script mã hóa mật khẩu bằng bcrypt
│       ├── tests/                        # Bộ kiểm thử tự động pytest (130 tests)
│       ├── config.ini.example            # File mẫu cấu hình kết nối database
│       ├── requirements.txt              # Danh sách thư viện cần thiết
│       └── requirements-dev.txt          # Danh sách thư viện dùng cho testing
└── README.md                             # Tài liệu hướng dẫn chính của dự án
```

---

## 📝 Giấy phép (License)

Dự án được phân phối dưới giấy phép mã nguồn mở **MIT License**.
