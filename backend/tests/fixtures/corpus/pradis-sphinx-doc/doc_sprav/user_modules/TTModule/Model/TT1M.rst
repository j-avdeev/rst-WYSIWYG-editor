============
Модель: TT1M
============

Библиотека: TTModule
^^^^^^^^^^^^^^^^^^^^

Имя на уровне решателя: TT1M
----------------------------

Аннотация: Truth table model
----------------------------


Обозначение: |TT1M|
-------------------
.. |TT1M| image:: ../../_image/TTModule.TT1M.png
   :alt: Truth table model




.. csv-table:: **Порты (степени свободы) компонента:**
   :header: "№","Обозначение порта", "Тип", "Наименование порта"
   :widths: 6, 24, 22, 48

   "1","In1", "base.DOF1", "In1"
   "2","In2", "base.DOF1", "In2"
   "3","Out1", "base.DOF1", "Out1"
   "4","Out2", "base.DOF1", "Out2"


.. csv-table:: **Пользовательские параметры модели**
   :header: "№","Параметр", "Тип", "Описание", "Значение по умолч."
   :widths: 6, 24, 20, 36, 14

   "1","InputsNumber", "base.real", "Number of inputs ", ""
   "2","OutputsNumber", "base.real", "Number of outputs", ""
   "3","Precision", "base.real", "Precision range of value (eps)", ""
   "4","SwitchingTime", "base.real", "Switching time", ""
   "5","TruthTable", "base.real", "Truth table in form: [ [ [Ci], [Si] ] , [] ] (type - ?)", ""




