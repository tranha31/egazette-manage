-- Egazette: schema MySQL 8 (utf8mb4). Ứng dụng tự tạo bảng khi khởi động (AUTO_CREATE_TABLES=true);
-- file này để tham khảo hoặc chạy tay.
-- Database tạo từ bản trước khi dùng MinIO: ứng dụng tự thêm 2 cột bên dưới khi khởi động; chạy tay thì:
--   ALTER TABLE announcements ADD COLUMN pdf_bucket VARCHAR(100) NOT NULL DEFAULT '';
--   ALTER TABLE announcements ADD COLUMN pdf_size INT NOT NULL DEFAULT 0;
-- Sau đó chạy `python -m app.migrate_pdfs` để đưa PDF cũ trên đĩa lên MinIO.

CREATE TABLE announcements (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tax_code VARCHAR(20) NOT NULL, 
	ann_type VARCHAR(10) NOT NULL, 
	posted_at DATETIME NOT NULL, 
	posted_date DATE NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	start_at VARCHAR(40) NOT NULL, 
	end_at VARCHAR(40) NOT NULL, 
	place VARCHAR(255) NOT NULL, 
	change_type VARCHAR(255) NOT NULL, 
	company_name VARCHAR(500) NOT NULL, 
	doc_tax_code VARCHAR(20) NOT NULL, 
	established_date DATE, 
	hq_address TEXT NOT NULL, 
	charter_capital VARCHAR(80) NOT NULL, 
	reg_change_date DATE, 
	reg_place VARCHAR(255) NOT NULL, 
	pdf_bucket VARCHAR(100) NOT NULL DEFAULT '', 
	pdf_path VARCHAR(500) NOT NULL, 
	pdf_size INTEGER NOT NULL DEFAULT 0, 
	pdf_status VARCHAR(255) NOT NULL, 
	parse_status VARCHAR(255) NOT NULL, 
	job_id INTEGER, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_ann UNIQUE (tax_code, ann_type, posted_at)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_ann_posted_date ON announcements (posted_date);
CREATE INDEX ix_ann_company ON announcements (company_name);

CREATE TABLE crawl_coverage (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tax_code VARCHAR(20) NOT NULL, 
	ann_type VARCHAR(10) NOT NULL, 
	date_from DATE NOT NULL, 
	date_to DATE NOT NULL, 
	crawled_at DATETIME NOT NULL, 
	job_id INTEGER, 
	result_count INTEGER NOT NULL, 
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_cov_tax_type ON crawl_coverage (tax_code, ann_type);

CREATE TABLE crawl_jobs (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	tax_code VARCHAR(20) NOT NULL, 
	ann_type VARCHAR(10) NOT NULL, 
	req_from DATE, 
	req_to DATE, 
	crawl_from DATE, 
	crawl_to DATE, 
	cover_from DATE, 
	cover_to DATE, 
	`force` BOOL NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	message TEXT NOT NULL, 
	log MEDIUMTEXT NOT NULL, 
	result_count INTEGER NOT NULL, 
	new_count INTEGER NOT NULL, 
	pdf_ok INTEGER NOT NULL, 
	pdf_fail INTEGER NOT NULL, 
	created_by VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	finished_at DATETIME, 
	PRIMARY KEY (id)
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_jobs_tax_type ON crawl_jobs (tax_code, ann_type);
CREATE INDEX ix_jobs_status ON crawl_jobs (status);

CREATE TABLE announcement_fields (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	announcement_id INTEGER NOT NULL, 
	seq INTEGER NOT NULL, 
	grp VARCHAR(255) NOT NULL, 
	field_key VARCHAR(255) NOT NULL, 
	field_value TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(announcement_id) REFERENCES announcements (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_fields_ann ON announcement_fields (announcement_id, seq);

CREATE TABLE legal_reps (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	announcement_id INTEGER NOT NULL, 
	seq INTEGER NOT NULL, 
	full_name VARCHAR(255) NOT NULL, 
	gender VARCHAR(20) NOT NULL, 
	position VARCHAR(255) NOT NULL, 
	birth_date DATE, 
	ethnicity VARCHAR(80) NOT NULL, 
	nationality VARCHAR(80) NOT NULL, 
	id_doc_type VARCHAR(120) NOT NULL, 
	id_number VARCHAR(40) NOT NULL, 
	id_issue_date DATE, 
	id_issue_place VARCHAR(255) NOT NULL, 
	residence_address TEXT NOT NULL, 
	contact_address TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(announcement_id) REFERENCES announcements (id) ON DELETE CASCADE
)CHARSET=utf8mb4 ENGINE=InnoDB COLLATE utf8mb4_unicode_ci;

CREATE INDEX ix_rep_ann ON legal_reps (announcement_id);
CREATE INDEX ix_rep_name ON legal_reps (full_name);
CREATE INDEX ix_rep_idnum ON legal_reps (id_number);

