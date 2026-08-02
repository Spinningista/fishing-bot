from aiogram.fsm.state import State, StatesGroup


class TripFlow(StatesGroup):
    # --- начало выезда ---
    choosing_date = State()
    entering_date = State()
    choosing_water = State()
    entering_new_water = State()
    confirming_water_match = State()
    choosing_spot = State()
    entering_new_spot = State()
    confirming_spot_match = State()
    choosing_condition = State()

    # --- цикл добавления улова ---
    choosing_lure = State()
    searching_lure = State()
    entering_new_lure_brand = State()
    entering_new_lure_category = State()
    entering_new_lure_type = State()
    entering_new_lure_model = State()
    confirming_lure_match = State()
    asking_lure_photo = State()
    waiting_lure_photo = State()

    choosing_species = State()
    entering_new_species = State()
    confirming_species_match = State()

    entering_qty = State()
    entering_weight = State()

    after_catch = State()  # "ещё улов" / "закончить выезд"
