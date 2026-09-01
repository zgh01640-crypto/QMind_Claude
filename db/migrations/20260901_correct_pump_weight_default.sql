-- 031005001 变频给水设备：修正知识库源数据中的设备重量默认范围。
-- 仅替换已确认错误的旧值，避免覆盖后续人工维护的正确记录。
UPDATE tqdk_tqdxmtz
SET defaulttzms = '设备重量W(t) 1＜W≤1.2',
    updated_at = NOW()
WHERE qdkid = 1020025
  AND qdzmid = 4067
  AND id = 10157
  AND tzmc = '质量'
  AND defaulttzms = '设备重量W(t) 0.4＜W≤0.6';
