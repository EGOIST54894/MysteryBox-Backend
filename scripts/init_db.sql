-- ============================================================
-- 外卖盲盒系统 - 数据库初始化脚本
-- 数据库: MySQL 8.0+
-- 引擎: InnoDB
-- 字符集: utf8mb4
-- 排序规则: utf8mb4_unicode_ci
-- ============================================================

-- 创建数据库（如不存在）
CREATE DATABASE IF NOT EXISTS mystery_box
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE mystery_box;

-- ============================================================
-- 1. 用户表 (user)
-- ============================================================
CREATE TABLE IF NOT EXISTS `user` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `phone`         VARCHAR(11)     NOT NULL                 COMMENT '手机号',
    `wechat_openid` VARCHAR(64)     DEFAULT NULL             COMMENT '微信OpenID',
    `nickname`      VARCHAR(50)     DEFAULT NULL             COMMENT '用户昵称',
    `avatar_url`    VARCHAR(500)    DEFAULT NULL             COMMENT '头像URL',
    `password_hash` VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `gender`        TINYINT         NOT NULL DEFAULT 0       COMMENT '性别: 0未知 1男 2女',
    `status`        TINYINT         NOT NULL DEFAULT 1       COMMENT '状态: 1正常 0禁用',
    `last_login_at` DATETIME        DEFAULT NULL             COMMENT '最后登录时间',
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_phone`         (`phone`),
    UNIQUE INDEX `uk_wechat_openid` (`wechat_openid`),
    INDEX        `idx_status`       (`status`),
    INDEX        `idx_created_at`   (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';


-- ============================================================
-- 2. 用户收货地址表 (user_address)
-- ============================================================
CREATE TABLE IF NOT EXISTS `user_address` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `user_id`       BIGINT          NOT NULL                 COMMENT '用户ID',
    `contact_name`  VARCHAR(30)     NOT NULL                 COMMENT '联系人姓名',
    `contact_phone` VARCHAR(11)     NOT NULL                 COMMENT '联系人电话',
    `province`      VARCHAR(20)     NOT NULL                 COMMENT '省份',
    `city`          VARCHAR(20)     NOT NULL                 COMMENT '城市',
    `district`      VARCHAR(20)     NOT NULL                 COMMENT '区/县',
    `detail`        VARCHAR(200)    NOT NULL                 COMMENT '详细地址',
    `latitude`      DECIMAL(10,7)   DEFAULT NULL             COMMENT '纬度',
    `longitude`     DECIMAL(10,7)   DEFAULT NULL             COMMENT '经度',
    `is_default`    TINYINT(1)      NOT NULL DEFAULT 0       COMMENT '是否默认地址',
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX        `idx_user_id`     (`user_id`),
    INDEX        `idx_is_default`  (`user_id`, `is_default`),
    CONSTRAINT   `fk_user_address_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户收货地址表';


-- ============================================================
-- 3. 商家表 (merchant)
-- ============================================================
CREATE TABLE IF NOT EXISTS `merchant` (
    `id`               BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `phone`            VARCHAR(11)     NOT NULL                 COMMENT '手机号',
    `password_hash`    VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `store_name`       VARCHAR(100)    NOT NULL                 COMMENT '店铺名称',
    `logo_url`         VARCHAR(500)    DEFAULT NULL             COMMENT '店铺Logo URL',
    `description`      TEXT            DEFAULT NULL             COMMENT '店铺描述',
    `category`         VARCHAR(50)     DEFAULT NULL             COMMENT '经营品类',
    `business_license` VARCHAR(500)    DEFAULT NULL             COMMENT '营业执照图片URL',
    `status`           TINYINT         NOT NULL DEFAULT 0       COMMENT '状态: 0待审核 1通过 2拒绝 3禁用',
    `latitude`         DECIMAL(10,7)   DEFAULT NULL             COMMENT '纬度',
    `longitude`        DECIMAL(10,7)   DEFAULT NULL             COMMENT '经度',
    `province`         VARCHAR(20)     DEFAULT NULL             COMMENT '所在省份',
    `city`             VARCHAR(20)     DEFAULT NULL             COMMENT '所在城市',
    `district`         VARCHAR(20)     DEFAULT NULL             COMMENT '所在区/县',
    `address_detail`   VARCHAR(200)    DEFAULT NULL             COMMENT '详细地址',
    `business_hours`   JSON            DEFAULT NULL             COMMENT '营业时间(JSON格式)',
    `rating_avg`       DECIMAL(2,1)    NOT NULL DEFAULT 0.0     COMMENT '平均评分',
    `created_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_phone`       (`phone`),
    INDEX        `idx_status`     (`status`),
    INDEX        `idx_city`       (`city`),
    INDEX        `idx_rating`     (`rating_avg`),
    INDEX        `idx_category`   (`category`),
    INDEX        `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='商家表';


-- ============================================================
-- 4. 配送人员表 (delivery_personnel)
-- ============================================================
CREATE TABLE IF NOT EXISTS `delivery_personnel` (
    `id`               BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `phone`            VARCHAR(11)     NOT NULL                 COMMENT '手机号',
    `password_hash`    VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `real_name`        VARCHAR(30)     NOT NULL                 COMMENT '真实姓名',
    `id_card`          VARCHAR(18)     NOT NULL                 COMMENT '身份证号',
    `status`           TINYINT         NOT NULL DEFAULT 0       COMMENT '状态: 0待审核 1在线 2离线 3禁用',
    `current_lat`      DECIMAL(10,7)   DEFAULT NULL             COMMENT '当前纬度',
    `current_lng`      DECIMAL(10,7)   DEFAULT NULL             COMMENT '当前经度',
    `rating_avg`       DECIMAL(2,1)    NOT NULL DEFAULT 0.0     COMMENT '平均评分',
    `completed_orders` INT             NOT NULL DEFAULT 0       COMMENT '已完成订单数',
    `created_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_phone`       (`phone`),
    INDEX        `idx_status`     (`status`),
    INDEX        `idx_rating`     (`rating_avg`),
    INDEX        `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='配送人员表';


-- ============================================================
-- 5. 管理员表 (admin)
-- ============================================================
CREATE TABLE IF NOT EXISTS `admin` (
    `id`            BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `username`      VARCHAR(50)     NOT NULL                 COMMENT '用户名',
    `password_hash` VARCHAR(255)    NOT NULL                 COMMENT '密码哈希',
    `role`          ENUM('admin','super_admin') NOT NULL DEFAULT 'admin' COMMENT '角色: admin普通管理员 super_admin超级管理员',
    `status`        TINYINT         NOT NULL DEFAULT 1       COMMENT '状态: 1正常 0禁用',
    `created_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_username` (`username`),
    INDEX        `idx_status`   (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='管理员表';


-- ============================================================
-- 6. 盲盒商品表 (mystery_box) — 核心表
-- ============================================================
CREATE TABLE IF NOT EXISTS `mystery_box` (
    `id`              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `merchant_id`     BIGINT          NOT NULL                 COMMENT '商家ID',
    `title`           VARCHAR(200)    NOT NULL                 COMMENT '盲盒标题',
    `description`     TEXT            DEFAULT NULL             COMMENT '盲盒描述',
    `cover_image`     VARCHAR(500)    DEFAULT NULL             COMMENT '封面图片URL',
    `box_type`        ENUM('surplus','group_buy','surprise') NOT NULL COMMENT '盲盒类型: surplus余量盲盒 group_buy拼团盲盒 surprise惊喜盲盒',
    `original_price`  DECIMAL(10,2)   NOT NULL                 COMMENT '原价',
    `sale_price`      DECIMAL(10,2)   NOT NULL                 COMMENT '售价',
    `stock`           INT             NOT NULL DEFAULT 0       COMMENT '当前库存',
    `total_stock`     INT             NOT NULL DEFAULT 0       COMMENT '总库存',
    `group_min_size`  INT             NOT NULL DEFAULT 0       COMMENT '拼团最小人数',
    `group_max_size`  INT             NOT NULL DEFAULT 0       COMMENT '拼团最大人数',
    `group_deadline`  DATETIME        DEFAULT NULL             COMMENT '拼团截止时间',
    `status`          TINYINT         NOT NULL DEFAULT 1       COMMENT '状态: 0下架 1上架 2售罄 3过期',
    `pick_up_start`   DATETIME        DEFAULT NULL             COMMENT '可取餐开始时间',
    `pick_up_end`     DATETIME        DEFAULT NULL             COMMENT '可取餐结束时间',
    `publish_at`      DATETIME        DEFAULT NULL             COMMENT '发布时间',
    `expired_at`      DATETIME        DEFAULT NULL             COMMENT '过期时间',
    `view_count`      INT             NOT NULL DEFAULT 0       COMMENT '浏览次数',
    `sale_count`      INT             NOT NULL DEFAULT 0       COMMENT '已售数量',
    `rating_avg`      DECIMAL(2,1)    NOT NULL DEFAULT 0.0     COMMENT '平均评分',
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX        `idx_merchant_id`   (`merchant_id`),
    INDEX        `idx_box_type`      (`box_type`),
    INDEX        `idx_status`        (`status`),
    INDEX        `idx_sale_price`    (`sale_price`),
    INDEX        `idx_rating`        (`rating_avg`),
    INDEX        `idx_publish_at`    (`publish_at`),
    INDEX        `idx_merchant_status` (`merchant_id`, `status`),
    INDEX        `idx_box_type_status` (`box_type`, `status`),
    INDEX        `idx_created_at`    (`created_at`),
    CONSTRAINT   `fk_mystery_box_merchant` FOREIGN KEY (`merchant_id`) REFERENCES `merchant` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='盲盒商品表';


-- ============================================================
-- 7. 盲盒标签表 (box_tag)
-- ============================================================
CREATE TABLE IF NOT EXISTS `box_tag` (
    `id`         BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `box_id`     BIGINT          NOT NULL                 COMMENT '盲盒ID',
    `tag_name`   VARCHAR(50)     NOT NULL                 COMMENT '标签名称',
    `created_at` DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_box_tag_name` (`box_id`, `tag_name`),
    INDEX        `idx_box_id`      (`box_id`),
    INDEX        `idx_tag_name`    (`tag_name`),
    CONSTRAINT   `fk_box_tag_mystery_box` FOREIGN KEY (`box_id`) REFERENCES `mystery_box` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='盲盒标签表';


-- ============================================================
-- 8. 用户偏好标签表 (user_preference)
-- ============================================================
CREATE TABLE IF NOT EXISTS `user_preference` (
    `id`         BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `user_id`    BIGINT          NOT NULL                 COMMENT '用户ID',
    `tag_name`   VARCHAR(50)     NOT NULL                 COMMENT '标签名称',
    `weight`     DECIMAL(5,2)    NOT NULL DEFAULT 1.00    COMMENT '偏好权重',
    `created_at` DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_user_tag_name` (`user_id`, `tag_name`),
    INDEX        `idx_user_id`      (`user_id`),
    INDEX        `idx_tag_name`     (`tag_name`),
    CONSTRAINT   `fk_user_preference_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户偏好标签表';


-- ============================================================
-- 9. 拼团群组表 (group_buy_group)
-- ============================================================
CREATE TABLE IF NOT EXISTS `group_buy_group` (
    `id`             BIGINT                                          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `box_id`         BIGINT                                          NOT NULL                 COMMENT '盲盒ID',
    `leader_user_id` BIGINT                                          NOT NULL                 COMMENT '团长用户ID',
    `current_size`   INT                                             NOT NULL DEFAULT 1       COMMENT '当前拼团人数',
    `target_size`    INT                                             NOT NULL                 COMMENT '目标拼团人数',
    `status`         ENUM('gathering','completed','expired','cancelled') NOT NULL DEFAULT 'gathering' COMMENT '拼团状态',
    `deadline`       DATETIME                                        NOT NULL                 COMMENT '拼团截止时间',
    `completed_at`   DATETIME                                        DEFAULT NULL             COMMENT '拼团完成时间',
    `created_at`     DATETIME                                        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`     DATETIME                                        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    INDEX        `idx_box_id`         (`box_id`),
    INDEX        `idx_leader_user_id` (`leader_user_id`),
    INDEX        `idx_status`         (`status`),
    INDEX        `idx_deadline`       (`deadline`),
    INDEX        `idx_box_status`     (`box_id`, `status`),
    CONSTRAINT   `fk_group_buy_box`   FOREIGN KEY (`box_id`)         REFERENCES `mystery_box` (`id`) ON DELETE CASCADE,
    CONSTRAINT   `fk_group_buy_leader` FOREIGN KEY (`leader_user_id`) REFERENCES `user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='拼团群组表';


-- ============================================================
-- 10. 订单表 (order) — 核心表
-- ============================================================
CREATE TABLE IF NOT EXISTS `order` (
    `id`              BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `order_no`        VARCHAR(32)     NOT NULL                 COMMENT '订单编号',
    `user_id`         BIGINT          NOT NULL                 COMMENT '用户ID',
    `box_id`          BIGINT          NOT NULL                 COMMENT '盲盒ID',
    `address_id`      BIGINT          DEFAULT NULL             COMMENT '地址ID',
    `quantity`        INT             NOT NULL DEFAULT 1       COMMENT '购买数量',
    `unit_price`      DECIMAL(10,2)   NOT NULL                 COMMENT '单价',
    `total_amount`    DECIMAL(10,2)   NOT NULL                 COMMENT '总金额',
    `discount_amount` DECIMAL(10,2)   NOT NULL DEFAULT 0.00    COMMENT '优惠金额',
    `paid_amount`     DECIMAL(10,2)   NOT NULL DEFAULT 0.00    COMMENT '实付金额',
    `group_id`        BIGINT          DEFAULT NULL             COMMENT '拼团ID',
    `group_role`      ENUM('leader','member') DEFAULT NULL     COMMENT '拼团角色: leader团长 member团员',
    `order_status`    ENUM('pending_pay','paid','confirmed','preparing','ready_pickup','delivering','delivered','completed','cancelled','refunding','refunded') NOT NULL DEFAULT 'pending_pay' COMMENT '订单状态',
    `cancel_reason`   VARCHAR(500)    DEFAULT NULL             COMMENT '取消原因',
    `paid_at`         DATETIME        DEFAULT NULL             COMMENT '支付时间',
    `confirmed_at`    DATETIME        DEFAULT NULL             COMMENT '确认时间',
    `delivered_at`    DATETIME        DEFAULT NULL             COMMENT '送达时间',
    `completed_at`    DATETIME        DEFAULT NULL             COMMENT '完成时间',
    `cancelled_at`    DATETIME        DEFAULT NULL             COMMENT '取消时间',
    `created_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_order_no`            (`order_no`),
    INDEX        `idx_user_id`            (`user_id`),
    INDEX        `idx_box_id`             (`box_id`),
    INDEX        `idx_address_id`         (`address_id`),
    INDEX        `idx_group_id`           (`group_id`),
    INDEX        `idx_order_status`       (`order_status`),
    INDEX        `idx_paid_at`            (`paid_at`),
    INDEX        `idx_created_at`         (`created_at`),
    INDEX        `idx_user_status`        (`user_id`, `order_status`),
    INDEX        `idx_box_status`         (`box_id`, `order_status`),
    INDEX        `idx_group_status`       (`group_id`, `order_status`),
    CONSTRAINT   `fk_order_user`          FOREIGN KEY (`user_id`)    REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT   `fk_order_box`           FOREIGN KEY (`box_id`)     REFERENCES `mystery_box` (`id`) ON DELETE RESTRICT,
    CONSTRAINT   `fk_order_address`       FOREIGN KEY (`address_id`) REFERENCES `user_address` (`id`) ON DELETE SET NULL,
    CONSTRAINT   `fk_order_group`         FOREIGN KEY (`group_id`)   REFERENCES `group_buy_group` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='订单表';


-- ============================================================
-- 11. 配送订单表 (delivery_order)
-- ============================================================
CREATE TABLE IF NOT EXISTS `delivery_order` (
    `id`                 BIGINT                                            NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `order_id`           BIGINT                                            NOT NULL                 COMMENT '订单ID',
    `delivery_person_id` BIGINT                                            DEFAULT NULL             COMMENT '配送员ID',
    `status`             ENUM('assigned','picked_up','delivering','delivered') NOT NULL DEFAULT 'assigned' COMMENT '配送状态',
    `assigned_at`        DATETIME                                          DEFAULT NULL             COMMENT '分配时间',
    `picked_up_at`       DATETIME                                          DEFAULT NULL             COMMENT '取货时间',
    `delivered_at`       DATETIME                                          DEFAULT NULL             COMMENT '送达时间',
    `created_at`         DATETIME                                          NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`         DATETIME                                          NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_order_id`            (`order_id`),
    INDEX        `idx_delivery_person_id` (`delivery_person_id`),
    INDEX        `idx_status`             (`status`),
    INDEX        `idx_person_status`      (`delivery_person_id`, `status`),
    CONSTRAINT   `fk_delivery_order_order`    FOREIGN KEY (`order_id`)           REFERENCES `order` (`id`) ON DELETE CASCADE,
    CONSTRAINT   `fk_delivery_order_person`   FOREIGN KEY (`delivery_person_id`) REFERENCES `delivery_personnel` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='配送订单表';


-- ============================================================
-- 12. 评价表 (review)
-- ============================================================
CREATE TABLE IF NOT EXISTS `review` (
    `id`           BIGINT          NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `order_id`     BIGINT          NOT NULL                 COMMENT '订单ID',
    `user_id`      BIGINT          NOT NULL                 COMMENT '用户ID',
    `box_id`       BIGINT          NOT NULL                 COMMENT '盲盒ID',
    `rating`       TINYINT         NOT NULL                 COMMENT '评分: 1~5',
    `content`      TEXT            DEFAULT NULL             COMMENT '评价内容',
    `images`       JSON            DEFAULT NULL             COMMENT '评价图片URL列表(JSON)',
    `is_anonymous` TINYINT(1)      NOT NULL DEFAULT 0       COMMENT '是否匿名',
    `status`       TINYINT         NOT NULL DEFAULT 1       COMMENT '状态: 1正常 0隐藏',
    `created_at`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_order_id`     (`order_id`),
    INDEX        `idx_user_id`     (`user_id`),
    INDEX        `idx_box_id`      (`box_id`),
    INDEX        `idx_rating`      (`rating`),
    INDEX        `idx_status`      (`status`),
    INDEX        `idx_box_rating`  (`box_id`, `rating`),
    CONSTRAINT   `fk_review_order` FOREIGN KEY (`order_id`) REFERENCES `order` (`id`) ON DELETE CASCADE,
    CONSTRAINT   `fk_review_user`  FOREIGN KEY (`user_id`)  REFERENCES `user` (`id`) ON DELETE CASCADE,
    CONSTRAINT   `fk_review_box`   FOREIGN KEY (`box_id`)   REFERENCES `mystery_box` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='评价表';


-- ============================================================
-- 13. 支付记录表 (payment_record)
-- ============================================================
CREATE TABLE IF NOT EXISTS `payment_record` (
    `id`             BIGINT                                      NOT NULL AUTO_INCREMENT  COMMENT '主键ID',
    `order_id`       BIGINT                                      NOT NULL                 COMMENT '订单ID',
    `transaction_no` VARCHAR(64)                                 NOT NULL                 COMMENT '第三方交易流水号',
    `pay_method`     ENUM('alipay','wechat_pay','mock')         NOT NULL                 COMMENT '支付方式: alipay支付宝 wechat_pay微信支付 mock模拟支付',
    `pay_amount`     DECIMAL(10,2)                               NOT NULL                 COMMENT '支付金额',
    `status`         ENUM('pending','success','failed','refunded') NOT NULL DEFAULT 'pending' COMMENT '支付状态',
    `paid_at`        DATETIME                                    DEFAULT NULL             COMMENT '支付时间',
    `raw_response`   JSON                                        DEFAULT NULL             COMMENT '第三方支付原始响应(JSON)',
    `created_at`     DATETIME                                    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at`     DATETIME                                    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE INDEX `uk_transaction_no` (`transaction_no`),
    INDEX        `idx_order_id`       (`order_id`),
    INDEX        `idx_status`         (`status`),
    INDEX        `idx_pay_method`     (`pay_method`),
    INDEX        `idx_paid_at`        (`paid_at`),
    CONSTRAINT   `fk_payment_order`   FOREIGN KEY (`order_id`) REFERENCES `order` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='支付记录表';


-- ============================================================
-- 初始化完成
-- ============================================================
-- 插入默认超级管理员（密码为 admin123，生产环境请修改）
-- 密码哈希使用 bcrypt 算法，此处为示例占位
-- INSERT INTO `admin` (`username`, `password_hash`, `role`, `status`)
-- VALUES ('admin', '$2b$12$...替换为实际哈希...', 'super_admin', 1);
