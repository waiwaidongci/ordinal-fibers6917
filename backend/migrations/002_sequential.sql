CREATE TABLE sequential_monitors (
	id INTEGER NOT NULL AUTO_INCREMENT,
	name VARCHAR(140) NOT NULL,
	study_id INTEGER NOT NULL,
	alpha DOUBLE NOT NULL,
	status VARCHAR(20) NOT NULL,
	plan_snapshot JSON NOT NULL,
	plan_fingerprint VARCHAR(64) NOT NULL,
	look_rule VARCHAR(60) NOT NULL,
	look_count INTEGER NOT NULL,
	last_evidence JSON NOT NULL,
	started_by VARCHAR(140) NOT NULL,
	started_at DATETIME NOT NULL,
	stopped_at DATETIME NULL,
	stopped_by VARCHAR(140) NOT NULL,
	stop_note VARCHAR(600) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (name),
	FOREIGN KEY(study_id) REFERENCES grade_studies (id)
)
;

CREATE TABLE sequential_looks (
	id INTEGER NOT NULL AUTO_INCREMENT,
	monitor_id INTEGER NOT NULL,
	look_index INTEGER NOT NULL,
	evidence JSON NOT NULL,
	readings_snapshot JSON NOT NULL,
	input_fingerprint VARCHAR(64) NOT NULL,
	created_by VARCHAR(140) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (monitor_id, look_index),
	FOREIGN KEY(monitor_id) REFERENCES sequential_monitors (id)
)
;
