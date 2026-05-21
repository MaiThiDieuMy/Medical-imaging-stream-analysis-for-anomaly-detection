# Tài liệu Thiết kế Hệ thống - Medical Imaging Analysis System

Tài liệu này tổng hợp các sơ đồ thiết kế cho hệ thống phân tích hình ảnh y tế streaming (X-ray/CT).

---

## 1.2 Sơ đồ chức năng tổng quát
```mermaid
mindmap
  root((CHỨC NĂNG TỔNG QUÁT))
    %% Nhóm 1
    1. QUẢN LÝ ẢNH (STORAGE)
      Tải ảnh lên hệ thống
      Kiểm tra định dạng ảnh
      Lưu trữ ảnh và metadata
      Xem lại ảnh đã tải lên
    %% Nhóm 2
    2. XỬ LÝ STREAMING
      Tiếp nhận ảnh vào hàng đợi
      Cập nhật trạng thái xử lý
      Xử lý nhiều ảnh liên tục
    %% Nhóm 3
    3. PHÂN TÍCH BẰNG MÔ HÌNH (INFERENCE)
      Tiền xử lý ảnh đầu vào
      Dự đoán bằng mô hình
    %% Nhóm 4
    4. QUẢN LÝ KẾT QUẢ PHÂN TÍCH
      Xem kết quả theo từng ảnh
      Lưu lịch sử phân tích
      Tìm kiếm kết quả
      Xuất báo cáo
    %% Nhóm 5
    5. QUẢN LÝ MÔ HÌNH MLOPS
      Quản lý phiên bản mô hình
      Lưu thông tin mô hình sử dụng
      Theo dõi chỉ số đánh giá
      Cập nhật mô hình mới
    %% Nhóm 6
    6. GIÁM SÁT HỆ THỐNG (MONITORING)
      Thống kê thông lượng xử lý (throughput)
      Theo dõi độ trễ (latency)
      Giám sát tài nguyên hệ thống
      Cảnh báo lỗi và sự cố
```

---

## 1.3 Usecase Diagram
```plantuml
@startuml
left to right direction
skinparam packageStyle rectangle

actor "User\n(Bác sĩ / KTV)" as User
actor "Admin\n(Quản trị viên)" as Admin

rectangle "HỆ THỐNG PHÂN TÍCH ẢNH Y TẾ" {

  (Đăng nhập) as UC_Login
  User --> UC_Login
  Admin --> UC_Login

  ' ===== USER =====
  (Tải ảnh lên hệ thống) as UC_Upload
  (Xem ảnh đã tải) as UC_ViewImage
  (Xem kết quả phân tích) as UC_ViewResult
  (Tìm kiếm kết quả) as UC_Search
  (Xuất báo cáo) as UC_Report

  User --> UC_Upload
  User --> UC_ViewImage
  User --> UC_ViewResult

  UC_ViewResult ..> UC_Search : <<extend>>
  UC_ViewResult ..> UC_Report : <<extend>>

  ' ===== RESULT =====
  (Lưu kết quả phân tích) as UC_Save
  (Lưu lịch sử phân tích) as UC_History

  UC_Upload --> UC_Save : <<include>>
  UC_Save --> UC_History : <<include>>

  ' ===== ADMIN =====
  (Quản lý mô hình) as UC_Model
  (Xem thông tin mô hình) as UC_ModelInfo
  (Cập nhật mô hình) as UC_UpdateModel
  (Theo dõi hiệu năng mô hình) as UC_ModelMetric

  Admin --> UC_Model

  UC_Model --> UC_ModelInfo : <<include>>
  UC_Model --> UC_UpdateModel : <<include>>
  UC_Model --> UC_ModelMetric : <<include>>

  ' ===== MONITORING =====
  (Giám sát hệ thống) as UC_Monitor
  (Xem hiệu năng hệ thống) as UC_SystemMetric
  (Nhận cảnh báo lỗi) as UC_Alert

  Admin --> UC_Monitor

  UC_Monitor --> UC_SystemMetric : <<include>>
  UC_Monitor --> UC_Alert : <<include>>
}
@enduml
```

---

## 1.4 Biểu đồ hoạt động (Activity Diagram)
```plantuml
@startuml
|Người dùng (Bác sĩ/KTV)|
start
:Tải ảnh X-quang lên hệ thống;

|Hệ thống (Pipeline & AI)|
:Kiểm tra định dạng và Metadata;
if (Hợp lệ?) then (Có)
  :Kiểm tra ảnh trong Cơ sở dữ liệu;
  if (Đã tồn tại kết quả?) then (Đã có)
    :Truy xuất kết quả cũ từ Database;
    |Người dùng (Bác sĩ/KTV)|
    :Hiển thị kết quả chẩn đoán (History);
    
  else (Chưa có)
    |Hệ thống (Pipeline & AI)|
    :Đưa ảnh vào hàng đợi (Queue);
    fork
      :Xử lý Streaming (Bất đồng bộ);
    fork again
      :Tiền xử lý ảnh (Resize/Normalize);
    end fork
    :Mô hình AI thực hiện Inference;
    :Trả kết quả (Nhãn & Confidence);
    |Người dùng (Bác sĩ/KTV)|
    :Xem kết quả chẩn đoán trên Dashboard;
    
    |Hệ thống (Pipeline & AI)|
    if (Confidence < 0.7?) then (Thấp)
      |Quản trị & MLOps|
      :Gắn cờ ca khó (Low Confidence);
      :Lưu vào bộ nhớ đệm Retrain;
      :Thông báo cho Admin/Bác sĩ gán nhãn lại;
    else (Cao)
      |Hệ thống (Pipeline & AI)|
      :Lưu kết quả vào Database;
      :Lưu lịch sử phân tích;
    endif
  endif
  |Người dùng (Bác sĩ/KTV)|
  :Xuất báo cáo y tế (tùy chọn);
else (Không)
  :Thông báo lỗi định dạng;
  stop
endif

|Hệ thống (Pipeline & AI)|
:Cập nhật chỉ số Monitoring (Throughput/Latency);
stop
@enduml
```

---

## 1.5 Biểu đồ trình tự (Sequence Diagram)
```mermaid
sequenceDiagram
    autonumber
    actor User as Bác sĩ / KTV
    participant Web as Giao diện Web
    participant API as Backend / API
    participant DB as CSDL bệnh nhân & ca chụp
    participant Storage as Kho lưu trữ ảnh
    participant Queue as Hàng đợi Streaming
    participant AI as Dịch vụ AI Inference

    User->>Web: 1. Upload ảnh X-quang và nhập thông tin bệnh nhân
    Web->>User: 2. Bấm Phân tích AI
    Web->>API: 3. Gửi thông tin bệnh nhân và ảnh
    
    activate API
    API->>API: 4. Tính image_hash
    API->>DB: 5. Kiểm tra kết quả theo image_hash + model_version
    
    alt Ảnh đã có kết quả
        DB-->>API: 6A. Trả kết quả đã có
        API-->>Web: 7A. Trả kết quả phân tích
        Web-->>User: 8A. Hiển thị kết quả AI
    else Ảnh chưa có kết quả
        API->>DB: 6B. Lưu / cập nhật hồ sơ bệnh nhân
        API->>Storage: 7B. Lưu tệp ảnh X-quang
        API->>DB: 8B. Tạo mã ca chụp, lưu metadata, status = queued
        API->>Queue: 9B. Đẩy job phân tích vào hàng đợi
        API-->>Web: 10B. Thông báo: Đã tiếp nhận xử lý
        Web-->>User: 11B. Hiển thị trạng thái chờ xử lý
        
        Queue->>AI: 12B. Worker nhận job phân tích
        activate AI
        AI->>Queue: 13B. Cập nhật status = processing
        AI->>Storage: 14B. Lấy ảnh X-quang
        Storage-->>AI: 15B. Trả tệp ảnh
        AI->>AI: 16B. Tiền xử lý ảnh và suy luận mô hình
        AI->>DB: 17B. Lưu kết quả AI, status = completed
        deactivate AI
        
        Web->>API: 18B. Yêu cầu lấy trạng thái / kết quả
        API->>DB: 19B. Truy vấn trạng thái và kết quả
        DB-->>API: 20B. Trả dữ liệu kết quả
        API-->>Web: 21B. Trả kết quả phân tích
        Web-->>User: 22B. Hiển thị kết quả AI
    end
    deactivate API
```

---

## 1.6 Biểu đồ lớp (Class Diagram)
```mermaid
classDiagram
    class User {
        <<abstract>>
        -userId: UUID
        -username: string
        -passwordHash: string
        -fullName: string
        -role: string
        +login()
        +logout()
    }

    class DoctorTechnician {
        <<entity>>
        -department: string
        +uploadXRay()
        +requestAnalysis()
        +viewResult()
    }

    class Admin {
        <<entity>>
        -adminLevel: string
        +manageModel()
        +viewMonitoring()
    }

    class Patient {
        <<entity>>
        -patientId: UUID
        -patientCode: string
        -fullName: string
        -gender: string
        -birthYear: int
        +updateInfo()
    }

    class XRayCase {
        <<entity>>
        -CaseId: UUID
        -status: string
        -createdAt: datetime
        -modelVersion: string
        -note: string
        +createCase()
        +updateStatus()
    }

    class XRayImage {
        <<entity>>
        -imageId: UUID
        -fileName: string
        -imagePath: string
        -imageHash: string
        -fileFormat: string
        -uploadedAt: datetime
        +calculateHash()
        +saveImage()
    }

    class AnalysisResult {
        <<entity>>
        -resultId: UUID
        -labelName: string
        -probability: float
        -predictedPositive: boolean
        -modelVersion: string
        -createdAt: datetime
        +saveResult()
    }

    class AnalysisJob {
        <<entity>>
        -jobId: UUID
        -status: string
        -createdAt: datetime
        -startedAt: datetime
        -finishedAt: datetime
        +createJob()
        +updateStatus()
    }

    class AIModel {
        <<entity>>
        -modelId: UUID
        -modelName: string
        -version: string
        -isActive: boolean
        +loadModel()
        +predict()
    }

    class StreamingQueue {
        <<service>>
        +enqueue(job)
        +dequeue()
        +ack()
    }

    class SystemMonitor {
        <<service>>
        +collectThroughput()
        +collectLatency()
        +monitorDataDrift()
        +alertError()
    }

    class ModelManager {
        <<service>>
        +registerModel()
        +setActiveModel()
        +trackModelMetric()
    }

    %% Relationships
    User <|-- DoctorTechnician
    User <|-- Admin
    Patient "1" -- "0..*" XRayCase : has
    DoctorTechnician "1" -- "0..*" XRayCase : creates
    XRayCase "1" *-- "1" XRayImage : contains
    XRayCase "1" -- "0..*" AnalysisResult : produces
    XRayCase "1" -- "0..1" AnalysisJob : triggers
    StreamingQueue "1" -- "0..*" AnalysisJob : manages
    SystemMonitor ..> AnalysisJob : tracks
    Admin ..> SystemMonitor : views
    AnalysisJob "0..*" -- "1" AIModel : uses
    Admin ..> ModelManager : manages
    ModelManager ..> AIModel : updates
```

---

## 1.7 Biểu đồ cơ sở dữ liệu (Database ERD)
```mermaid
erDiagram
    users {
        UUID user_id PK
        VARCHAR_50 username
        VARCHAR_255 password_hash
        VARCHAR_100 full_name
        ENUM role "user, admin"
        TIMESTAMP created_at
    }

    patients {
        UUID patient_id PK
        VARCHAR_20 patient_code
        VARCHAR_100 full_name
        VARCHAR_10 gender
        INT birth_year
        VARCHAR_100 department
        TIMESTAMP created_at
    }

    xray_cases {
        UUID case_id PK
        UUID patient_id FK
        UUID uploaded_by FK
        ENUM status "queued, processing, completed, failed"
        TEXT note
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    xray_images {
        UUID image_id PK
        UUID case_id FK "UNIQUE"
        VARCHAR_255 file_name
        TEXT image_path
        VARCHAR_64 image_hash
        VARCHAR_20 file_format
        TIMESTAMP uploaded_at
    }

    analysis_jobs {
        UUID job_id PK
        UUID case_id FK "UNIQUE"
        UUID model_id FK
        ENUM status "queued, processing, completed, failed"
        VARCHAR_100 worker_id
        TEXT error_message
        TIMESTAMP created_at
        TIMESTAMP started_at
        TIMESTAMP finished_at
    }

    analysis_results {
        UUID result_id PK
        UUID case_id FK
        UUID model_id FK
        VARCHAR_100 label_name
        FLOAT probability
        BOOLEAN predicted_positive
        TIMESTAMP created_at
    }

    ai_models {
        UUID model_id PK
        VARCHAR_100 model_name
        VARCHAR_20 version
        TEXT model_path
        FLOAT accuracy
        FLOAT f1_score
        FLOAT precision_score
        FLOAT recall_score
        BOOLEAN is_active
        TIMESTAMP created_at
    }

    %% Relationships
    users ||--o{ xray_cases : "uploads / creates"
    patients ||--o{ xray_cases : "has"
    xray_cases ||--|| xray_images : "contains"
    xray_cases ||--o{ analysis_results : "produces"
    xray_cases ||--|| analysis_jobs : "triggers"
    ai_models ||--o{ analysis_results : "generates"
    ai_models ||--o{ analysis_jobs : "used by"
```

---