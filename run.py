from multiprocessing import freeze_support
import sys
from fw_ddsm.iteration import *
from fw_ddsm.output import *
from pandas import DataFrame
import os
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import smtplib

algorithms = dict()
algorithms[m_minizinc] = dict()
algorithms[m_minizinc][m_before_fw] = m_minizinc
algorithms[m_minizinc][m_after_fw] = f"{m_minizinc}_fw"
algorithms[m_ogsa] = dict()
algorithms[m_ogsa][m_before_fw] = m_ogsa
algorithms[m_ogsa][m_after_fw] = f"{m_ogsa}_fw"

# penalty_weight_range = [0, 5, 50, 500, 5000, 50000]
# num_tasks_dependent_range = [0, 3, 5]
# num_households_range = [50, 100, 500, 1000, 2000, 4000, 6000, 8000, 10000]
num_households_range = [50]
penalty_weight_range = [5]
# num_tasks_dependent_range = [0, 2, 4, 6, 8]
num_tasks_dependent_range = [3]
num_full_flex_tasks = 0
num_semi_flex_tasks = 10
num_fixed_tasks = 0
num_samples = 5
num_repeat = 1
id_job = 0
battery_usages = [True, False]
battery_solver_choice = "gurobi"
battery_fully_charged_hour = 5

# read_from_date_time = "2020-11-25_23-16-39"
name_exp = None
# cpus_nums = None

cpus_nums = cpu_count()
ensure_dependent = True
experiment_tracker = dict()
timeout = 120
min_step_size = 0.0005
ignore_tiny_step = True
roundup_tiny_step = False
print_done = False
print_steps = False
email_results = True


def main(num_households, num_tasks_dependent, penalty_weight, out, new_data=True, num_cpus=None, job_id=0,
         use_battery=False):
    num_experiment = 0
    # read_from_date_time = "2020-11-25_23-16-39"
    print("----------------------------------------")
    param_str = f"{num_households} households, " \
                f"{int(use_battery)} battery, " \
                f"{num_tasks_dependent} dependent tasks, " \
                f"{num_full_flex_tasks} fully flexible tasks, " \
                f"{num_semi_flex_tasks} semi-flexible tasks, " \
                f"{num_fixed_tasks} fixed tasks, " \
                f"{penalty_weight} penalty weight. "
    print(param_str)
    print("----------------------------------------")

    new_iteration = Iteration()
    output_folder, output_parent_folder, this_date_time \
        = out.new_output_folder(num_households=num_households,
                                num_dependent_tasks=num_tasks_dependent,
                                num_full_flex_task_min=num_full_flex_tasks,
                                num_semi_flex_task_min=num_semi_flex_tasks,
                                inconvenience_cost_weight=penalty_weight,
                                folder_id=job_id,
                                use_battery=use_battery)
    plots_demand_layout = []
    plots_demand_finalised_layout = []
    for alg in algorithms.values():
        while num_experiment in experiment_tracker:
            num_experiment += 1
        experiment_tracker[num_experiment] = dict()
        experiment_tracker[num_experiment][k_households_no] = num_households
        experiment_tracker[num_experiment][k_penalty_weight] = penalty_weight
        experiment_tracker[num_experiment][k_dependent_tasks_no] = num_tasks_dependent
        experiment_tracker[num_experiment][h_tasks_no_ff_min] = num_full_flex_tasks
        experiment_tracker[num_experiment][h_tasks_no_sf_min] = num_semi_flex_tasks
        experiment_tracker[num_experiment][h_tasks_no_fixed_min] = num_fixed_tasks
        experiment_tracker[num_experiment][m_algorithm] = alg[m_after_fw]
        experiment_tracker[num_experiment]["id"] = job_id

        if use_battery:
            experiment_tracker[num_experiment][b_cap_max] = battery_capacity_max
            experiment_tracker[num_experiment][b_cap_min] = battery_capacity_min
            experiment_tracker[num_experiment][b_power] = battery_power

        # 1. iteration data
        if new_data:
            preferred_demand_profile, prices = \
                new_iteration.new(algorithm=alg, num_households=num_households,
                                  max_demand_multiplier=maximum_demand_multiplier,
                                  num_tasks_dependent=num_tasks_dependent, ensure_dependent=ensure_dependent,
                                  full_flex_task_min=num_full_flex_tasks, full_flex_task_max=0,
                                  semi_flex_task_min=num_semi_flex_tasks, semi_flex_task_max=0,
                                  fixed_task_min=num_fixed_tasks, fixed_task_max=0,
                                  inconvenience_cost_weight=penalty_weight,
                                  max_care_factor=care_f_max,
                                  data_folder=output_parent_folder,
                                  date_time=this_date_time,
                                  capacity_max=battery_capacity_max, capacity_min=battery_capacity_min,
                                  power=battery_power)
            new_data = False
        else:
            if m_ogsa in alg:
                num_tasks_dependent = None
                penalty_weight = None

            # read_from_date_time = read_from_date_time
            read_from_date_time = this_date_time
            preferred_demand_profile, prices = \
                new_iteration.read(algorithm=alg, inconvenience_cost_weight=penalty_weight,
                                   new_dependent_tasks=num_tasks_dependent,
                                   ensure_dependent=ensure_dependent,
                                   read_from_folder=output_parent_folder,
                                   date_time=read_from_date_time)

        # 2. iteration begins
        start_time_probability, num_iterations = \
            new_iteration.begin_iteration(starting_prices=prices,
                                          use_battery=use_battery,
                                          battery_solver=battery_solver_choice,
                                          num_cpus=num_cpus,
                                          timeout=timeout,
                                          fully_charge_time=battery_fully_charged_hour,
                                          min_step_size=min_step_size,
                                          ignore_tiny_step=ignore_tiny_step,
                                          roundup_tiny_step=roundup_tiny_step,
                                          print_done=print_done, print_steps=print_steps)
        experiment_tracker[num_experiment][k_iteration_no] = num_iterations

        # 3. finalising schedules
        new_iteration.finalise_schedules(num_samples=num_samples,
                                         start_time_probability=start_time_probability)

        # 4. preparing plots and writing results to CSVs
        plots_demand, plots_demand_finalised, overview_dict \
            = out.save_to_output_folder(algorithm=alg,
                                        aggregator_tracker=new_iteration.aggregator.tracker,
                                        aggregator_final=new_iteration.aggregator.final,
                                        community_tracker=new_iteration.community.tracker,
                                        community_final=new_iteration.community.final)
        plots_demand_layout.append(plots_demand)
        plots_demand_finalised_layout.append(plots_demand_finalised)
        experiment_tracker[num_experiment].update(overview_dict)

    # 5. drawing all plots
    print("----------------------------------------")
    output_file(f"{output_folder}{this_date_time}_plots.html")
    tab1 = Panel(child=layout(plots_demand_layout), title="FW-DDSM results")
    tab2 = Panel(child=layout(plots_demand_finalised_layout), title="Actual schedules")
    div = Div(text=f"""{param_str}""", width=800)
    save(layout([div], [Tabs(tabs=[tab2, tab1])]))

    # 6. writing experiment overview
    df_exp = DataFrame.from_dict(experiment_tracker).transpose()
    # df_exp[s_obj] = df_exp[s_penalty] + df_exp[p_cost]
    df_exp.to_csv(r"{}{}_overview.csv".format(output_parent_folder, this_date_time))
    with open(f"{out.output_parent_folder}data/{this_date_time}_{file_experiment_pkl}",
              'wb+') as f:
        pickle.dump(experiment_tracker, f, pickle.HIGHEST_PROTOCOL)
    print("----------------------------------------")

    print("----------------------------------------")
    print("Experiment is finished. ")
    print(df_exp[[k_households_no, k_dependent_tasks_no, k_penalty_weight,
                  m_algorithm, k_iteration_no, s_par_init, s_par,
                  s_demand_reduction, p_cost_reduction]])

    # if email_results:
    #     msg = MIMEMultipart()
    #     body_part = MIMEText(param_str, 'plain')
    #     msg['Subject'] = "Experiment@Nectar completed. "
    #     msg['From'] = "dora.he3@monash.edu"
    #     msg['To'] = "dora.he3@monash.edu"
    #     # Add body to email
    #     msg.attach(body_part)
    #     # open and read the CSV file in binary
    #     with open("{}{}_overview.csv".format(output_parent_folder, this_date_time), 'rb') as file:
    #         # Attach the file with filename to the email
    #         msg.attach(MIMEApplication(file.read(), Name="overview.csv"))

    # Create SMTP object
    # smtp_obj = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    # # Login to the server
    # smtp_obj.login(SMTP_USERNAME, SMTP_PASSWORD)
    #
    # # Convert the message to a string and send it
    # smtp_obj.sendmail(msg['From'], msg['To'], msg.as_string())
    # smtp_obj.quit()


if __name__ == '__main__':
    freeze_support()
    print(f"Arguments count: {len(sys.argv)}")

    # try:
    for i, arg in enumerate(sys.argv):
        print(f"Argument {i:>6}: {arg}")

        if i == 1:
            cpus_nums = int(arg)
        elif i == 2:
            num_households_range = [int(arg)]
        elif i == 3:
            penalty_weight_range = [int(arg)]
        elif i == 4:
            num_tasks_dependent_range = [int(arg)]
        elif i == 5:
            id_job = int(arg)
        elif i == 6:
            name_exp = str(arg)

    out1 = Output(output_root_folder="results", output_parent_folder=name_exp)

    for r in range(num_repeat):
        new = True
        for h in num_households_range:
            for w in penalty_weight_range:
                for dt in num_tasks_dependent_range:
                    for battery_use in battery_usages:
                        main(new_data=new,
                             num_households=h,
                             num_tasks_dependent=dt,
                             penalty_weight=w,
                             out=out1,
                             num_cpus=cpus_nums,
                             job_id=r,
                             use_battery=battery_use)
                        new = False
    # except Exception as e:
    #     print(e.args)
    #     print()
