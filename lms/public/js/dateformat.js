function formatDate(date) {
  var months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];
  var day = date.getDate();
  var year = date.getFullYear();
  var month = months[date.getMonth()];
  return day + " " + month + " " + year;
}
