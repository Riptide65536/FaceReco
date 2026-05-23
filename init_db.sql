CREATE DATABASE IF NOT EXISTS db_bishe DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE db_bishe;

CREATE TABLE IF NOT EXISTS accounts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS recognition_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100),
    location VARCHAR(100),
    timestamp DATETIME,
    emotion VARCHAR(20),
    attendance_type VARCHAR(20),
    status VARCHAR(20),
    image_path VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS face_features (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100),
    label INT,
    feature_path VARCHAR(255)
);
