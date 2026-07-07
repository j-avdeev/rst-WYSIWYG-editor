============
Модель: TT2M
============

Библиотека: TTModule
^^^^^^^^^^^^^^^^^^^^

Имя на уровне решателя: TT2M
----------------------------

Аннотация: Truth table model
----------------------------


Обозначение: |TT2M|
-------------------
.. |TT2M| image:: ../../_image/TTModule.TT2M.png
   :alt: Truth table model




.. csv-table:: **Порты (степени свободы) компонента:**
   :header: "№","Обозначение порта", "Тип", "Наименование порта"
   :widths: 6, 24, 22, 48

   "1","In1", "base.DOF1", "In1"
   "2","In2", "base.DOF1", "In2"
   "3","In3", "base.DOF1", "In3"
   "4","In4", "base.DOF1", "In4"
   "5","Out1", "base.DOF1", "Out1"
   "6","Out2", "base.DOF1", "Out2"
   "7","Out3", "base.DOF1", "Out3"
   "8","Out4", "base.DOF1", "Out4"


.. csv-table:: **Пользовательские параметры модели**
   :header: "№","Параметр", "Тип", "Описание", "Значение по умолч."
   :widths: 6, 24, 20, 36, 14

   "1","InputsNumber", "base.real", "Number of inputs ", ""
   "2","OutputsNumber", "base.real", "Number of outputs", ""
   "3","Precision", "base.real", "Precision range of value (eps)", ""
   "4","SwitchingTime", "base.real", "Switching time", ""
   "5","TruthTable", "base.real", "Truth table in form: [ [ [Ci], [Si] ] , [] ] (type - ?)", ""




